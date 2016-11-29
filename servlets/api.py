import datetime
import feedparser
import json
import logging
import time
import urllib

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from googleapiclient.discovery import build

import app
import base_servlet
import event_types
from event_scraper import add_entities
from events import add_events
from events import eventdata
import fb_api
import keys
from loc import formatting
from loc import gmaps_api
from loc import math
from search import onebox
from search import search
from search import search_base
from users import user_creation
from users import users
from util import urls

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATETIME_FORMAT_TZ = "%Y-%m-%dT%H:%M:%S%z"


def get_user_id_for_token(access_token):
    key = 'AccessTokenToID: %s' % access_token
    user_id = memcache.get(key)
    if not user_id:
        result = fb_api.FBAPI(access_token).get('me', {'fields': 'id'})
        user_id = result['id']
        memcache.set(key, user_id)
    return user_id


class ApiHandler(base_servlet.BareBaseRequestHandler):
    requires_auth = False
    supports_auth = False

    def requires_login(self):
        return False

    def write_json_error(self, error_result):
        return self._write_json_data(error_result)

    def write_json_success(self, results=None):
        if results is None:
            results = {'success': True}
        return self._write_json_data(results)

    def _write_json_data(self, json_data):
        callback = self.request.get('callback')
        if callback:
            self.response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        else:
            self.response.headers['Content-Type'] = 'application/json; charset=utf-8'

        if callback:
            self.response.out.write('%s(' % callback)
        self.response.out.write(json.dumps(json_data))
        if callback:
            self.response.out.write(')')

    def _initialize(self, request):
        # We use _initialize instead of webapp2's initialize, so that exceptions can be caught easily
        self.fbl = fb_api.FBLookup(None, None)

        if self.request.body:
            logging.info("Request body: %r", self.request.body)
            escaped_body = urllib.unquote_plus(self.request.body.strip('='))
            self.json_body = json.loads(escaped_body)
            logging.info("json_request: %r", self.json_body)
        else:
            self.json_body = None

        if self.requires_auth or self.supports_auth:
            if self.json_body.get('access_token'):
                access_token = self.json_body.get('access_token')
                self.fb_uid = get_user_id_for_token(access_token)
                self.fbl = fb_api.FBLookup(self.fb_uid, access_token)
                logging.info("Access token for user ID %s", self.fb_uid)
            elif self.requires_auth:
                self.add_error("Needs access_token parameter")

    def dispatch(self):
        try:
            major_version, minor_version = self.request.route_args[0:2]
            self.request.route_args = self.request.route_args[2:]
            self.version = (int(major_version), int(minor_version))
            self._initialize(self.request)
            super(ApiHandler, self).dispatch()
        except Exception as e:
            logging.exception("API failure")
            result = e.args and e.args[0] or e
            # If it's a string or a regular object
            if not hasattr(result, '__iter__'):
                result = [result]
            self.write_json_error({'success': False, 'errors': [unicode(x) for x in result]})


def apiroute(path, *args, **kwargs):
    return app.route('/api/v(\d+)\.(\d+)' + path, *args, **kwargs)


class RetryException(Exception):
    pass


def retryable(func):
    def wrapped_func(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self = args[0]
            logging.exception("API retry failure")
            url = self.request.path
            body = self.request.body
            logging.error(e)
            logging.error("Retrying URL %s", url)
            logging.error("With Payload %r", body)
            taskqueue.add(method='POST', url=url, payload=body, countdown=60 * 60)
            raise
    return wrapped_func

@apiroute('/search')
class SearchHandler(ApiHandler):

    def _get_title(self, location, keywords):
        if location:
            if keywords:
                return "Events near %s containing %s" % (location, keywords)
            else:
                return "Events near %s" % location
        else:
            if keywords:
                return "Events containing %s" % keywords
            else:
                return "Events"

    def get(self):
        data = {
            'location': self.request.get('location'),
            'keywords': self.request.get('keywords'),
            'locale': self.request.get('locale'),
        }
        # If it's 1.0 clients, or web clients, then grab all data
        if self.version == (1, 0):
            time_period = search_base.TIME_UPCOMING
        else:
            time_period = self.request.get('time_period')
        data['time_period'] = time_period
        form = search_base.SearchForm(data=data)

        if not form.validate():
            for field, errors in form.errors.items():
                for error in errors:
                    self.add_error(u"%s error: %s" % (
                        getattr(form, field).label.text,
                        error
                    ))

        if not form.location.data:
            city_name = None
            southwest = None
            northeast = None
            if not form.keywords.data:
                if self.version == (1, 0):
                    self.write_json_success({'results': []})
                    return
                else:
                    self.add_error('Please enter a location or keywords')
        else:
            place = gmaps_api.fetch_place_as_json(query=form.location.data, language=form.locale.data)
            if place['status'] == 'OK' and place['results']:
                geocode = gmaps_api.GMapsGeocode(place['results'][0])
                southwest, northeast = math.expand_bounds(geocode.latlng_bounds(), form.distance_in_km())
                city_name = place['results'][0]['formatted_address']
                # This will fail on a bad location, so let's verify the location is geocodable above first.
            else:
                if self.version == (1, 0):
                    self.write_json_success({'results': []})
                    return
                else:
                    self.add_error('Could not geocode location')

        self.errors_are_fatal()

        search_results = []
        distances = [50, 100, 170, 300]
        distance_index = 0
        while not search_results:
            form.distance.data = distances[distance_index]
            form.distance_units.data = 'miles'
            search_query = form.build_query()
            searcher = search.Search(search_query)
            # TODO(lambert): Increase the size limit when our clients can handle it. And improve our result sorting to return the 'best' results.
            searcher.limit = 500
            search_results = searcher.get_search_results(full_event=True)

            # Increase our search distance in the hopes of finding something
            distance_index += 1
            if distance_index == len(distances):
                # If we searched the world, then break
                break

        logging.info("Found %r events within %s %s of %s", form.keywords.data, form.distance.data, form.distance_units.data, form.location.data)
        onebox_links = onebox.get_links_for_query(search_query)

        json_results = []
        for result in search_results:
            try:
                json_result = canonicalize_event_data(result.db_event, result.event_keywords, self.version)
                json_results.append(json_result)
            except Exception as e:
                logging.exception("Error processing event %s: %s" % (result.event_id, e))

        title = self._get_title(city_name, form.keywords.data)

        json_response = {
            'results': json_results,
            'onebox_links': onebox_links,
            'title': title,
            'location': city_name,
            'query': data,
        }
        if southwest and northeast:
            json_response['location_box'] = {
                'southwest': {
                    'latitude': southwest[0],
                    'longitude': southwest[1],
                },
                'northeast': {
                    'latitude': northeast[0],
                    'longitude': northeast[1],
                },
            }
        self.write_json_success(json_response)
    post = get


def update_user(servlet, user, json_body):
    location = json_body.get('location')
    if location:
        # If we had a geocode failure, or had a geocode bug, or we did a geocode bug and only got a country
        user.location = location
    else:
        # Use the IP address headers if we've got nothing better
        if not user.location:
            user.location = servlet.get_location_from_headers()

    if not getattr(user, 'json_data', None):
        user.json_data = {}
    android_token = json_body.get('android_device_token')
    if android_token:
        tokens = user.device_tokens('android')
        if android_token not in tokens:
            tokens.append(android_token)
    ios_token = json_body.get('ios_device_token')
    if ios_token:
        tokens = user.device_tokens('ios')
        if android_token not in tokens:
            tokens.append(android_token)


# Released a version of iOS that requested from /api/v1.1auth, so let's handle that here for awhile
@apiroute('/auth')
class AuthHandler(ApiHandler):
    requires_auth = True

    @retryable
    def post(self):
        access_token = self.json_body.get('access_token')
        if not access_token:
            self.write_json_error({'success': False, 'errors': ['No access token']})
            logging.error("Received empty access_token from client. Payload was: %s", self.json_body)
            return
        self.errors_are_fatal() # Assert that our access_token is set

        # Fetch the access_token_expires value from Facebook, instead of demanding it via the API
        debug_info = fb_api.lookup_debug_tokens([access_token])[0]
        if debug_info['empty']:
            logging.error('Error: %s', debug_info['empty'])
            raise Exception(debug_info['empty'])
        access_token_expires_timestamp = debug_info['token']['data'].get('expires_at')
        if access_token_expires_timestamp:
            access_token_expires = datetime.datetime.fromtimestamp(access_token_expires_timestamp)
        else:
            access_token_expires = None

        logging.info("Auth tokens is %s", access_token)

        user = users.User.get_by_id(self.fb_uid)
        if user:
            logging.info("User exists, updating user with new fb access token data")
            user.fb_access_token = access_token
            user.fb_access_token_expires = access_token_expires
            user.expired_oauth_token = False
            user.expired_oauth_token_reason = ""

            client = self.json_body.get('client')
            if client and client not in user.clients:
                user.clients.append(client)

            # Track usage stats
            if user.last_login_time < datetime.datetime.now() - datetime.timedelta(hours=1):
                if user.login_count:
                    user.login_count += 1
                else:
                    user.login_count = 2 # once for this one, once for initial creation
            user.last_login_time = datetime.datetime.now()

            update_user(self, user, self.json_body)

            user.put() # this also sets to memcache
        else:
            client = self.json_body.get('client')
            location = self.json_body.get('location')
            fb_user = self.fbl.get(fb_api.LookupUser, 'me')
            user_creation.create_user_with_fbuser(self.fb_uid, fb_user, access_token, access_token_expires, location, client=client)
        self.write_json_success()


@apiroute('/user')
class UserUpdateHandler(ApiHandler):
    requires_auth = True

    def post(self):
        self.errors_are_fatal() # Assert that our access_token is set

        user = users.User.get_by_id(self.fb_uid)
        if not user:
            raise RetryException("User does not yet exist, cannot modify it yet.")

        update_user(self, user, self.json_body)

        user.put() # this also sets to memcache
        self.write_json_success()


class SettingsHandler(ApiHandler):
    requires_auth = True

    def get(self):
        user = users.User.get_by_id(self.fb_uid)
        json_data = {
            'location': user.location,
            'distance': user.distance,
            'distance_units': user.distance_units,
            'send_email': user.send_email,
        }
        self.write_json_success(json_data)

    def post(self):
        user = users.User.get_by_id(self.fb_uid)
        json_request = json.loads(self.request.body)
        if json_request.get('location'):
            user.location = json_request.get('location')
        if json_request.get('distance'):
            user.distance = json_request.get('distance')
        if json_request.get('distance_units'):
            user.distance_units = json_request.get('distance_units')
        if json_request.get('send_email'):
            user.send_email = json_request.get('send_email')
        user.put()

        self.write_json_success()


def canonicalize_event_data(db_event, event_keywords, version):
    event_api = {}
    event_api['id'] = db_event.id
    event_api['name'] = db_event.name
    event_api['start_time'] = db_event.start_time_with_tz.strftime(DATETIME_FORMAT_TZ)
    event_api['description'] = db_event.description
    # end time can be optional, especially on single-day events that are whole-day events
    if db_event.end_time_with_tz:
        event_api['end_time'] = db_event.end_time_with_tz.strftime(DATETIME_FORMAT_TZ)
    else:
        event_api['end_time'] = None
    event_api['source'] = {
        'name': db_event.source_name,
        'url': db_event.source_url,
    }

    # cover images
    if db_event.has_image:
        if version >= (1, 3):
            cover = db_event.cover_images[0]
            # Used by new react builds
            event_api['picture'] = {
                'source': urls.event_image_url(db_event.id),
                'width': cover['width'],
                'height': cover['height'],
            }
        else:
            if db_event.json_props:
                ratio = 1.0 * db_event.json_props['photo_width'] / db_event.json_props['photo_height']
            else:
                cover = db_event.cover_images[0]
                ratio = 1.0 * cover['width'] / cover['height']
            # Covers the most common screen sizes, according to Mixpanel:
            widths = reversed([320, 480, 720, 1080, 1440])
            cover_images = [{'source': urls.event_image_url(db_event.id, width=width), 'width': width, 'height': int(width/ratio)} for width in widths]

            # Used by old android and ios builds
            event_api['picture'] = urls.event_image_url(db_event.id, width=200, height=200)
            # Used by old react builds
            event_api['cover'] = {
                'cover_id': 'dummy', # Android (v1.1) expects this value, even though it does nothing with it.
                'images': sorted(cover_images, key=lambda x: -x['height']),
            }
    else:
        event_api['picture'] = None
        event_api['cover'] = None

    # location data
    if db_event.location_name:
        venue_location_name = db_event.location_name
    # We could do something like this...
    # elif db_event and db_event.actual_city_name:
    #    venue_location_name = db_event.actual_city_name
    # ...but really, this would return the overridden/remapped address name, which would likely just be a "City" anyway.
    # A city isn't particularly useful for our clients trying to display the event on a map.
    else:
        # In these very rare cases (where we've manually set the location on a location-less event), return ''
        # TODO: We'd ideally like to return None, but unfortunately Android expects this to be non-null in 1.0.3 and earlier.
        venue_location_name = ""
    venue = db_event.venue
    if 'name' in venue and venue['name'] != venue_location_name:
        logging.error("For event %s, venue name %r is different from location name %r", db_event.fb_event_id, venue['name'], venue_location_name)
    venue_id = None
    if 'id' in venue:
        venue_id = venue['id']
    address = None
    if 'country' in venue:
        address = {}
        for key in ['street', 'city', 'state', 'zip', 'country']:
            if key in venue:
                address[key] = venue.get(key)
    geocode = None
    if db_event.longitude and db_event.latitude:
        geocode = {
            'longitude': db_event.longitude,
            'latitude': db_event.latitude,
        }
    # I have seen:
    # - no venue subfields at all (ie, we manually specify the address/location in the event or remapping), which will be returned as "" here (see above comment)
    # - name only (possibly remapped?)
    # - name and id and geocode
    # - name and address and id and geocode
    # - name and address (everything except zip) and id and geocode
    # - so now address can be any subset of those fields that the venue author filled out...but will specify country, at least
    # ...are there more variations? write a mapreduce on recent events to check?
    event_api['venue'] = {
        'name': venue_location_name,
        'id': venue_id,
        'address': address,
        'geocode': geocode,
    }
    # people data
    event_api['admins'] = db_event.admins

    annotations = {}
    if db_event and db_event.creation_time:
        annotations['creation'] = {
            'time': db_event.creation_time.strftime(DATETIME_FORMAT),
            'method': db_event.creating_method,
            'creator': str(db_event.creating_fb_uid) if db_event.creating_fb_uid else None, #STR_ID_MIGRATE
        }
    # We may have keywords from the search result that called us
    if event_keywords:
        annotations['dance_keywords'] = event_keywords
        annotations['categories'] = event_keywords
    # or from the db_event associated with this
    elif db_event:
        annotations['dance_keywords'] = db_event.event_keywords
    # or possibly none at all, if we only received a fb_event..
    else:
        pass
    if db_event: # TODO: When is this not true?
        annotations['categories'] = event_types.humanize_categories(db_event.auto_categories)

    event_api['annotations'] = annotations
    event_api['ticket_uri'] = db_event.ticket_uri
    # maybe handle: 'timezone', 'updated_time'
    # rsvp_fields = ['attending_count', 'declined_count', 'maybe_count', 'noreply_count']
    if db_event.attending_count or db_event.maybe_count:
        event_api['rsvp'] = {
            'attending_count': db_event.attending_count or 0,
            'maybe_count': db_event.maybe_count or 0,
        }
    else:
        event_api['rsvp'] = None

    return event_api


@apiroute('/user/info')
class UserInfoHandler(ApiHandler):
    requires_auth = True

    def get(self):
        self.errors_are_fatal()

        user = users.User.get_by_id(self.fb_uid)
        if not user:
            results = {
                'location': '',
                'creation_time': datetime.datetime.now().strftime(DATETIME_FORMAT_TZ),
                'num_auto_added_events': 0,
                'num_auto_added_own_events': 0,
                'num_hand_added_events': 0,
                'num_hand_added_own_events': 0,
            }
        else:
            results = {
                'location': user.location,
                'creation_time': user.creation_time.strftime(DATETIME_FORMAT_TZ),
                'num_auto_added_events': user.num_auto_added_events,
                'num_auto_added_own_events': user.num_auto_added_own_events,
                'num_hand_added_events': user.num_hand_added_events,
                'num_hand_added_own_events': user.num_hand_added_own_events,
            }
        self.write_json_success(results)
    post = get


@apiroute('/events_translate')
class EventTranslateHandler(ApiHandler):
    requires_auth = True

    def post(self):
        if self.json_body:
            event_id = self.json_body.get('event_id')
            language = self.json_body.get('language') or self.json_body.get('locale')
            if not event_id:
                self.add_error('Need to pass event_id argument')
            if not language:
                self.add_error('Need to pass language/locale argument')
        else:
            self.add_error('Need to pass a post body of json params')
        # Remap our traditional/simplified chinese languages
        if language == 'zh':
            language = 'zh-TW'
        elif language == 'zh-Hant':
            language = 'zh-TW'
        elif language == 'zh-Hans':
            language = 'zh-CN'
        self.errors_are_fatal()
        db_event = eventdata.DBEvent.get_by_id(event_id)
        service = build('translate', 'v2', developerKey=keys.get('google_server_key'))
        result = service.translations().list(
            target=language,
            format='text',
            q=[db_event.name or '', db_event.description or '']
        ).execute()
        translations = [x['translatedText'] for x in result['translations']]
        self.write_json_success({'name': translations[0], 'description': translations[1]})
    get = post


@apiroute('/events_list_to_add')
class ListAddHandler(ApiHandler):
    requires_auth = True

    def post(self):
        events = add_events.get_decorated_user_events(self.fbl)
        self.write_json_success({'events': events})


@apiroute('/events_add')
class EventAddHandler(ApiHandler):
    requires_auth = True

    def post(self):
        event_id = self.json_body.get('event_id')
        if not event_id:
            self.add_error('Need to pass event_id argument')
        self.errors_are_fatal()
        fb_event = self.fbl.get(fb_api.LookupEvent, event_id, allow_cache=False)
        add_entities.add_update_event(fb_event, self.fbl, creating_uid=self.fbl.fb_uid, creating_method=eventdata.CM_USER)
        self.write_json_success()


@apiroute(r'/events/%s' % urls.EVENT_ID_REGEX)
class EventHandler(ApiHandler):
    def get(self):
        path_bits = self.request.path.split('/events/')
        if len(path_bits) != 2:
            self.add_error('Path is malformed: %s' % self.request.path)
            self.response.out.write('Need an event_id.')
            return
        else:
            event_id = urllib.unquote_plus(path_bits[1].strip('/'))
            db_event = eventdata.DBEvent.get_by_id(event_id)
            if not db_event:
                self.add_error('No event found')
            elif not db_event.has_content():
                self.add_error('This event was empty: %s.' % db_event.empty_reason)

        self.errors_are_fatal()
        # '?locale=' + self.request.get('locale')
        # get venue address and stuffs
        # pass in as rewritten db_event for computing json_data

        json_data = canonicalize_event_data(db_event, None, self.version)

        # Ten minute expiry on data we return
        self.response.headers['Cache-Control'] = 'max-age=%s' % (60 * 10)
        self.write_json_success(json_data)
    post = get

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


class DateHandlingJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, time.struct_time):
            return time.strftime(DATETIME_FORMAT, o)
        else:
            return json.JSONEncoder.default(self, o)


@apiroute(r'/feed')
class FeedHandler(ApiHandler):
    def get(self):
        if self.json_body:
            url = self.json_body.get('url')
        else:
            url = self.request.get('url')
        feed = feedparser.parse(url)
        json_string = json.dumps(feed, cls=DateHandlingJSONEncoder)
        json_data = json.loads(json_string)
        self.write_json_success(json_data)

    post = get

import random
from firebase import firebase
auth = firebase.FirebaseAuthentication(keys.get('firebase_secret'), None)
db = firebase.FirebaseApplication('https://dancedeets-hrd.firebaseio.com', auth)
#result = db.get('/events', None)
#print result

@apiroute(r'/event_signups/register')
class RegisterHandler(ApiHandler):
    supports_auth = True

    def post(self):
        event_id = self.json_body.get('event_id')
        category_id = self.json_body.get('category_id')
        team = self.json_body.get('team')
        team_name = team.get('team_name')

        dancers = {}
        dancer_index = 1
        while team.get('dancer_name_%s' % dancer_index):
            dancer_name = team.get('dancer_name_%s' % dancer_index)
            dancer_id = team.get('dancer_id_%s' % dancer_index) or dancer_name
            dancers[dancer_id] = {'name': dancer_name}
            dancer_index += 1

        event = db.get('/events', event_id)
        category_index = [index for (index, elem) in enumerate(event['categories']) if elem['id'] == category_id][0]

        signup_id = '%s_%s' % (int(time.time()), random.randint(10000, 99999))
        signup = {
            'teamName': team_name,
            'dancers': dancers,
        }
        db.put('/events/%s/categories/%s/signups/' % (event_id, category_index), signup_id, signup)
        self.write_json_success()

@apiroute(r'/event_signups/unregister')
class UnregisterHandler(ApiHandler):
    supports_auth = True

    def post(self):
        event_id = self.json_body.get('event_id')
        category_id = self.json_body.get('category_id')
        signup_id = self.json_body.get('signup_id')

        event = db.get('/events', event_id)
        category_index = [index for (index, elem) in enumerate(event['categories']) if elem['id'] == category_id][0]
        signup = event['categories'][category_index]['signups'][signup_id]
        authenticated = self.fb_uid in signup['dancers']
        if authenticated:
            db.delete('/events/%s/categories/%s/signups' % (event_id, category_index), signup_id)
            self.write_json_success()
        else:
            self.write_json_error('not authorized to delete signup')
