import logging

from google.appengine.ext import db
from google.appengine.runtime import apiproxy_errors

import cities
import datetime
import locations
import smemcache
from util import dates

USER_EXPIRY = 24 * 60 * 60

class User(db.Model):
    # SSO
    fb_uid = property(lambda x: int(x.key().name()))
    fb_access_token = db.StringProperty()

    # Statistics
    creation_time = db.DateTimeProperty()
    last_login_time = db.DateTimeProperty()
    login_count = db.IntegerProperty()
    inviting_fb_uid = db.IntegerProperty()

    # Search preferences
    location = db.StringProperty()
    distance = db.StringProperty()
    distance_units = db.StringProperty()
    min_attendees = db.IntegerProperty()

    # TODO(lambert): Get rid of these eventually??
    dance_type = db.StringProperty()
    freestyle = db.StringProperty()
    choreo = db.StringProperty()

    # Other preferences
    send_email = db.BooleanProperty()
    location_country = db.StringProperty()

    # Derived from fb_user
    full_name = db.StringProperty()
    email = db.StringProperty()

    expired_oauth_token = db.BooleanProperty()

    def distance_in_km(self):
        if not self.distance:
            return 0
        elif self.distance_units == 'km':
            return int(self.distance)
        else:
            return locations.miles_in_km(int(self.distance))

    @staticmethod
    def memcache_user_key(fb_user_id):
        return 'User.%s' % fb_user_id

    @classmethod
    def get_cached(cls, uid):
        memcache_key = cls.memcache_user_key(uid)
        user = smemcache.get(memcache_key)
        if not user:
            user = User.get_by_key_name(str(uid))
            if user:
                smemcache.set(memcache_key, user, USER_EXPIRY)
        return user

    def date_human_format(self, d):
        return dates.date_human_format(d, country=self.location_country)
    def duration_human_format(self, d1, d2):
        return dates.duration_human_format(d1, d2, country=self.location_country)

    def compute_derived_properties(self, fb_user):
        self.full_name = fb_user['profile']['name']
        self.email = fb_user['profile'].get('email')
        if self.location:
            #TODO(lambert): wasteful dual-lookups, but two memcaches aren't that big a deal given how infrequently this is called
            self.location_country = locations.get_country_for_location(self.location)
            closest_city = cities.get_closest_city(self.location)
        else:
            self.location_country = None

    def _populate_internal_entity(self):
        memcache_key = self.memcache_user_key(self.fb_uid)
        smemcache.set(memcache_key, self, USER_EXPIRY)
        return super(User, self)._populate_internal_entity()

    def get_city(self):
        if self.location:
            #TODO(lambert): cache this user city!
            user_city = cities.get_largest_nearby_city_name(self.location)
            return user_city
        else:
            return None

    def add_message(self, message):
        user_message = UserMessage(
            fb_uid=self.fb_uid,
            creation_time=datetime.datetime.now(),    
            message=message,
        )
        try:
            user_message.put()
        except apiproxy_errors.CapabilityDisabledError:
            pass
        return user_message

    def get_and_purge_messages(self):
        user_messages = UserMessage.gql("WHERE fb_uid = :fb_uid ORDER BY creation_time", fb_uid=self.fb_uid).fetch(100)
        messages = [x.message for x in user_messages]
        for user_message in user_messages:
            user_message.delete()
        return messages

class UserFriendsAtSignup(db.Model):
    fb_uid = property(lambda x: int(x.key().name()))
    registered_friend_ids = db.ListProperty(int)

class UserMessage(db.Model):
    fb_uid = db.IntegerProperty()
    creation_time = db.DateTimeProperty()
    message = db.TextProperty()


