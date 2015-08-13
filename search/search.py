#!/usr/bin/env python

import collections
import datetime
import logging
import pprint
import re
import time

from google.appengine.ext import deferred
from google.appengine.ext import ndb
from google.appengine.api import search

from events import eventdata
from loc import gmaps_api
from loc import math
from nlp import categories
from util import dates
from . import search_base

SLOW_QUEUE = 'slow-queue'

ALL_EVENTS_INDEX = 'AllEvents'
FUTURE_EVENTS_INDEX = 'FutureEvents'

MAX_EVENTS = 100000

class ResultsGroup(object): 
    def __init__(self, name, id, results, expanded, force=False): 
        self.name = name 
        self.id = id 
        self.results = results 
        self.expanded = expanded 
        self.force = force 

def group_results(search_results): 
    now = datetime.datetime.now() - datetime.timedelta(hours=12)

    grouped_results = [] 
    past_results = [] 
    present_results = [] 
    week_results = [] 
    month_results = [] 
    year_results = []
    past_index = 0
    future_index = 0
    for result in search_results: 
        if result.start_time < now:
            result.index = past_index
            past_index += 1
            if result.fake_end_time > now:
                present_results.append(result)
            else: 
                past_results.append(result) 
        else:
            result.index = future_index
            future_index += 1
            if result.start_time < now + datetime.timedelta(days=7): 
                week_results.append(result)
            elif result.start_time < now + datetime.timedelta(days=30): 
                month_results.append(result)
            else: 
                year_results.append(result) 
    grouped_results.append(ResultsGroup('Events This Week', 'week_events', week_results, expanded=True)) 
    grouped_results.append(ResultsGroup('Events This Month', 'month_events', month_results, expanded=True)) 
    grouped_results.append(ResultsGroup('Future Events', 'year_events', year_results, expanded=True)) 
    grouped_results = [x for x in grouped_results if x.results]
    return past_results, present_results, grouped_results 

class DisplayEvent(ndb.Model):
    """Subset of event data used for rendering"""
    fb_event_id = property(lambda x: str(x.key.string_id()))

    data = ndb.JsonProperty()

    @classmethod
    def can_build_from(cls, db_event):
        """Can we build a DisplayEvent from a given DBEvent"""
        if not db_event.fb_event:
            return False
        elif db_event.fb_event['empty']:
            return False
        else:
            return True

    @classmethod
    def build(cls, db_event):
        """Save off the minimal set of data necessary to render an event, for quick event loading."""
        if not cls.can_build_from(db_event):
            return None
        try:
            display_event = cls(id=db_event.fb_event_id)
            # The event_keywords are actually _BaseValue objects, not strings.
            # So they fail json serialization, and must be converted manually here.
            keywords = [unicode(x) for x in db_event.event_keywords]
            display_event.data = {
                'name': db_event.fb_event['info'].get('name'),
                'image': eventdata.get_event_image_url(db_event.fb_event),
                'cover': eventdata.get_largest_cover(db_event.fb_event),
                'start_time': db_event.fb_event['info']['start_time'],
                'end_time': db_event.fb_event['info'].get('end_time'),
                'location': db_event.actual_city_name,
                'lat': db_event.latitude,
                'lng': db_event.longitude,
                'attendee_count': db_event.attendee_count,
                'keywords': keywords or [],
            }
            return display_event
        except:
            logging.exception("Failed to construct DisplayEvent for event %s", db_event.fb_event_id)
            logging.error("FB Event data is:\n%s", pprint.pformat(db_event.fb_event, width=200))
            return None

    @classmethod
    def get_by_ids(cls, id_list, keys_only=False):
        if not id_list:
            return []
        keys = [ndb.Key(cls, x) for x in id_list]
        if keys_only:
            return cls.query(cls.key.IN(keys)).fetch(len(keys), keys_only=True)
        else:
            return ndb.get_multi(keys)

class SearchResult(object):
    def __init__(self, display_event, db_event):
        self.display_event = display_event
        self.db_event = db_event # May be None

        self.fb_event_id = display_event.fb_event_id
        self.name = display_event.data['name']
        self.actual_city_name = display_event.data['location']
        self.latitude = display_event.data['lat']
        self.longitude = display_event.data['lng']
        self.event_keywords = display_event.data['keywords']
        self.attendee_count = display_event.data['attendee_count']
        fake_event = {'info': {
            'start_time': display_event.data['start_time'],
            'end_time': display_event.data['end_time'],
        }}
        self.start_time = dates.parse_fb_start_time(fake_event)
        self.end_time = dates.parse_fb_end_time(fake_event)
        self.fake_end_time = dates.parse_fb_end_time(fake_event, need_result=True)

        self.rsvp_status = "unknown"
        # These are initialized in logic/friends.py
        self.attending_friend_count = 0
        self.attending_friends = []

        self.index = None

    def event_keywords_string(self):
        return ', '.join(self.event_keywords)

    def multi_day_event(self):
        return not self.end_time or (self.end_time - self.start_time) > datetime.timedelta(hours=24)

    def get_image(self):
        return self.display_event.data['image']

    def get_attendance(self):
        if self.rsvp_status == 'unsure':
            return 'maybe'
        return self.rsvp_status

class SearchQuery(object):
    def __init__(self, time_period=None, start_time=None, end_time=None, bounds=None, min_attendees=None, keywords=None):
        self.time_period = time_period

        self.min_attendees = min_attendees
        self.start_time = start_time
        self.end_time = end_time
        if self.start_time and self.end_time:
            assert self.start_time < self.end_time
        if self.time_period in search_base.FUTURE_INDEX_TIMES and self.end_time:
                assert self.end_time > datetime.datetime.now()
        if self.time_period in search_base.FUTURE_INDEX_TIMES and self.start_time:
                assert self.start_time < datetime.datetime.now()
        self.bounds = bounds

        if keywords:
            unquoted_quoted_keywords = re.sub(r'[<=>:(),]', ' ', keywords).split('"')
            for i in range(0, len(unquoted_quoted_keywords), 2):
                unquoted_quoted_keywords[i] = categories.format_as_search_query(unquoted_quoted_keywords[i])
            reconstructed_keywords = '"'.join(unquoted_quoted_keywords)
            self.keywords = reconstructed_keywords
        else:
            self.keywords = None

        self.limit = 1000

        # Extra search index fields to return
        self.extra_fields = []

    @classmethod
    def create_from_query(cls, query, start_end_query=False):
        if query.location:
            if query.distance_units == 'miles':
                distance_in_km = math.miles_in_km(query.distance)
            else:
                distance_in_km = query.distance
            geocode = gmaps_api.get_geocode(address=query.location)
            bounds = math.expand_bounds(geocode.latlng_bounds(), distance_in_km)
        else:
            bounds = None
        if start_end_query:
            self = cls(bounds=bounds, min_attendees=query.min_attendees, keywords=query.keywords, start_time=query.start_time, end_time=query.end_time)
        else:
            time_period = query.time_period
            self = cls(bounds=bounds, min_attendees=query.min_attendees, keywords=query.keywords, time_period=time_period)
        return self

    DATE_SEARCH_FORMAT = '%Y-%m-%d'
    def _get_candidate_doc_events(self, ids_only=True):
        clauses = []
        if self.bounds:
            # We try to keep searches as simple as possible, 
            # using just AND queries on latitude/longitude.
            # But for stuff crossing +/-180 degrees,
            # we need to do an OR longitude query on each side.
            latitudes = (self.bounds[0][0], self.bounds[1][0])
            longitudes = (self.bounds[0][1], self.bounds[1][1])
            clauses += ['latitude >= %s AND latitude <= %s' % latitudes]
            if longitudes[0] < longitudes[1]:
                clauses += ['longitude >= %s AND longitude <= %s' % longitudes]
            else:
                clauses += ['(longitude >= %s OR longitude <= %s)' % longitudes]
        index_name = ALL_EVENTS_INDEX
        if self.time_period:
            if self.time_period in search_base.FUTURE_INDEX_TIMES:
                index_name = FUTURE_EVENTS_INDEX
        if self.start_time:
            # Do we want/need this hack?
            if self.start_time > datetime.datetime.now():
                index_name = FUTURE_EVENTS_INDEX
            clauses += ['end_time >= %s' % self.start_time.date().strftime(self.DATE_SEARCH_FORMAT)]
        if self.end_time:
            clauses += ['start_time <= %s' % self.end_time.date().strftime(self.DATE_SEARCH_FORMAT)]
        if self.keywords:
            clauses += ['(%s)' % self.keywords]
        if self.min_attendees:
            clauses += ['attendee_count > %d' % self.min_attendees]
        if clauses:
            full_search = ' '.join(clauses)
            logging.info("Doing search for %r", full_search)
            doc_index = search.Index(name=index_name)
            #TODO(lambert): implement pagination
            if ids_only:
                options = {'returned_fields': ['start_time', 'end_time']}
            else:
                options = {'returned_fields': self.extra_fields}
            options = search.QueryOptions(limit=self.limit, **options)
            query = search.Query(query_string=full_search, options=options)
            doc_search_results = doc_index.search(query)
            return doc_search_results.results
        return []

    def get_search_results(self, fbl, prefilter=None, full_event=False):
        a = time.time()
        # Do datastore filtering
        doc_events = self._get_candidate_doc_events(ids_only=not prefilter)
        logging.info("Search returned %s events in %s seconds", len(doc_events), time.time() - a)

        #TODO(lambert): move to common library.
        now = datetime.datetime.now() - datetime.timedelta(hours=12)
        if self.time_period == search_base.TIME_ONGOING:
            doc_events = [x for x in doc_events if x.field('start_time').value < now]
        elif self.time_period == search_base.TIME_UPCOMING:
            doc_events = [x for x in doc_events if x.field('start_time').value > now]
        elif self.time_period == search_base.TIME_PAST:
            doc_events = [x for x in doc_events if x.field('end_time').value < now]

        if prefilter:
            doc_events = [x for x in doc_events if prefilter(x)]

        a = time.time()
        ids = [x.doc_id for x in doc_events]
        if full_event:
            real_db_events = eventdata.DBEvent.get_by_ids(ids)
            display_events =[DisplayEvent.build(x) for x in real_db_events]
        else:
            #This roundabout logic below is temporary while we load events, and wait for all events to be saved
            #display_events = DisplayEvent.get_by_ids(ids)
            real_db_events = [None for x in ids]

            display_event_lookup = dict(zip(ids, DisplayEvent.get_by_ids(ids)))
            missing_ids = [x for x in display_event_lookup if not display_event_lookup[x]]
            if missing_ids:
                dbevents = eventdata.DBEvent.get_by_ids(missing_ids)
                objs_to_put = []
                for event in dbevents:
                    display_event = DisplayEvent.build(event)
                    if display_event:
                        objs_to_put.append(display_event)
                    else:
                        logging.warning("Skipping event %s because no DisplayEvent", event.fb_event_id)
                ndb.put_multi(objs_to_put)
            display_events = [display_event_lookup[x] for x in ids]

        logging.info("Loading DBEvents took %s seconds", time.time() - a)

        # ...and do filtering based on the contents inside our app
        a = time.time()
        search_results = []
        for display_event, db_event in zip(display_events, real_db_events):
            if not display_event:
                continue
            result = SearchResult(display_event, db_event)
            search_results.append(result)
        logging.info("SearchResult construction took %s seconds, giving %s results", time.time() - a, len(search_results))
    
        existing_datetime_locs = collections.defaultdict(lambda: [])
        for r in search_results:
            if r.db_event:
                # This only works on full-events, aka API v1.0:
                r_datetime = r.db_event.start_time
                fb_event = r.db_event.fb_event
                venue = fb_event['info'].get('venue')
                # We only want to allow one event per time per specific-location
                if venue and venue.get('street'):
                    r_location = venue['id']
                else:
                    r_location = r.display_event.fb_event_id
                existing_datetime_locs[(r_datetime, r_location)].append(r)
            else:
                existing_datetime_locs[r.display_event.fb_event_id].append(r)

        deduped_results = []
        for same_results in existing_datetime_locs.values():
            largest_result = max(same_results, key=lambda x: x.attendee_count)
            deduped_results.append(largest_result)

        # Now sort and return the results
        a = time.time()
        deduped_results.sort(key=lambda x: x.start_time)
        logging.info("search result sorting took %s seconds", time.time() - a)
        return deduped_results

def update_fulltext_search_index(db_event, fb_event):
    update_fulltext_search_index_batch((db_event, fb_event))

def update_fulltext_search_index_batch(events_to_update):
    all_index = []
    all_deindex_ids = []
    future_index = []
    future_deindex_ids = []
    for db_event, fb_event in events_to_update:
        logging.info("Adding event to search index: %s", db_event.fb_event_id)
        doc_event = _create_doc_event(db_event, fb_event)
        if not doc_event:
            all_deindex_ids.append(db_event.fb_event_id)
            future_deindex_ids.append(db_event.fb_event_id)
        elif db_event.search_time_period == dates.TIME_FUTURE:
            all_index.append(doc_event)
            future_index.append(doc_event)
        else:
            all_index.append(doc_event)
            future_deindex_ids.append(db_event.fb_event_id)
    doc_index = search.Index(name=ALL_EVENTS_INDEX)
    doc_index.put(all_index)
    doc_index.delete(all_deindex_ids)
    doc_index = search.Index(name=FUTURE_EVENTS_INDEX)
    doc_index.put(future_index)
    doc_index.delete(future_deindex_ids)

def delete_from_fulltext_search_index(db_event_id):
    logging.info("Deleting event from search index: %s", db_event_id)
    doc_index = search.Index(name=ALL_EVENTS_INDEX)
    doc_index.delete(db_event_id)
    doc_index = search.Index(name=FUTURE_EVENTS_INDEX)
    doc_index.delete(db_event_id)

def construct_fulltext_search_index(fbl, index_future=True):
    logging.info("Loading DB Events")
    if index_future:
        db_query = eventdata.DBEvent.query(eventdata.DBEvent.search_time_period==dates.TIME_FUTURE)
    else:
        db_query = eventdata.DBEvent.query()
    db_event_keys = db_query.fetch(MAX_EVENTS, keys_only=True)
    db_event_ids = set(x.string_id() for x in db_event_keys)

    logging.info("Found %s db event ids for indexing", len(db_event_ids))
    if len(db_event_ids) >= MAX_EVENTS:
        logging.critical('Found %s events. Increase the MAX_EVENTS limit to search more events.', MAX_EVENTS)
    logging.info("Loaded %s DB Events", len(db_event_ids))

    index_name = index_future and FUTURE_EVENTS_INDEX or ALL_EVENTS_INDEX
    doc_index = search.Index(name=index_name)

    docs_per_group = search.MAXIMUM_DOCUMENTS_PER_PUT_REQUEST

    logging.info("Deleting Expired DB Events")
    start_id = '0'
    doc_ids_to_delete = set()
    while True:
        doc_ids = [x.doc_id for x in doc_index.get_range(ids_only=True, start_id=start_id, include_start_object=False)]
        if not doc_ids:
            break
        new_ids_to_delete = set(doc_ids).difference(db_event_ids)
        doc_ids_to_delete.update(new_ids_to_delete)
        logging.info("Looking at %s doc_id candidates for deletion, will delete %s entries.", len(doc_ids), len(new_ids_to_delete))
        start_id = doc_ids[-1]
    if len(doc_ids_to_delete) and len(doc_ids_to_delete) < len(db_event_ids) / 10:
        logging.critical("Deleting %s docs, more than 10% of total %s docs", len(doc_ids_to_delete), len(db_event_ids))
    logging.info("Deleting %s Events", len(doc_ids_to_delete))
    doc_ids_to_delete = list(doc_ids_to_delete)
    for i in range(0,len(doc_ids_to_delete), docs_per_group):
        doc_index.delete(doc_ids_to_delete[i:i+docs_per_group])

    # Add all events
    logging.info("Loading %s FB Events, in groups of %s", len(db_event_ids), docs_per_group)
    db_event_ids_list = list(db_event_ids)
    for i in range(0,len(db_event_ids_list), docs_per_group):
        group_db_event_ids = db_event_ids_list[i:i+docs_per_group]
        deferred.defer(save_db_event_ids, fbl, index_name, group_db_event_ids)

def _create_doc_event(db_event, fb_event):
    if fb_event['empty']:
        return None
    # TODO(lambert): find a way to index no-location events.
    # As of now, the lat/long number fields cannot be None.
    # In what radius/location should no-location events show up
    # and how do we want to return them
    # Perhaps a separate index that is combined at search-time?
    if db_event.latitude is None:
        return None
    # If this event has been deleted from Facebook, let's skip re-indexing it here
    if db_event.start_time is None:
        return None
    if not isinstance(db_event.start_time, datetime.datetime) and not isinstance(db_event.start_time, datetime.date):
        logging.error("DB Event %s start_time is not correct format: ", db_event.fb_event_id, db_event.start_time)
        return None
    doc_event = search.Document(
        doc_id=db_event.fb_event_id,
        fields=[
            search.TextField(name='name', value=fb_event['info'].get('name', '')),
            search.TextField(name='description', value=fb_event['info'].get('description', '')),
            search.NumberField(name='attendee_count', value=db_event.attendee_count or 0),
            search.DateField(name='start_time', value=db_event.start_time),
            search.DateField(name='end_time', value=dates.faked_end_time(db_event.start_time, db_event.end_time)),
            search.NumberField(name='latitude', value=db_event.latitude),
            search.NumberField(name='longitude', value=db_event.longitude),
            search.TextField(name='categories', value=' '.join(db_event.auto_categories)),
            search.TextField(name='country', value=db_event.country),
        ],
        #language=XX, # We have no good language detection
        rank=int(time.mktime(db_event.start_time.timetuple())),
        )
    return doc_event

def save_db_event_ids(fbl, index_name, db_event_ids):
    # TODO(lambert): how will we ensure we only update changed events?
    logging.info("Loading %s DB Events", len(db_event_ids))
    db_events = eventdata.DBEvent.get_by_ids(db_event_ids)
    if None in db_events:
        logging.error("DB Event Lookup returned None!")
    logging.info("Loading %s FB Events", len(db_event_ids))

    delete_ids = []
    doc_events = []
    logging.info("Constructing Documents")
    for db_event in db_events:
        doc_event = _create_doc_event(db_event, db_event.fb_event)
        if not doc_event:
            delete_ids.append(db_event.fb_event_id)
            continue
        doc_events.append(doc_event)

    logging.info("Adding %s documents", len(doc_events))
    doc_index = search.Index(name=index_name)
    doc_index.put(doc_events)

    # These events could not be filtered out too early,
    # but only after looking up in this db+fb-event-data world
    logging.info("Cleaning up and deleting %s documents", len(delete_ids))
    doc_index.delete(delete_ids)
