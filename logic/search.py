#!/usr/bin/env python

import datetime
import logging
import time
import smemcache

from google.appengine.ext import db
from google.appengine.ext import deferred

import base_servlet
from events import cities
from events import eventdata
from events import users
import fb_api
import locations
from logic import event_classifier
from logic import rsvp
from util import dates
from util import timings

SLOW_QUEUE = 'slow-queue'

class FrontendSearchQuery(object):
    def __init__(self):
        self.location = None
        self.distance = 50
        self.distance_units = 'miles'
        self.min_attendees = 0
        self.past = 0

    def url_params(self):
        return {
            'location': self.location,
            'distance': self.distance,
            'distance_units': self.distance_units,
            'min_attendees': self.min_attendees,
            'past': self.past,
        }

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
            if result.end_time > now:
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

class SearchResult(object):
    def __init__(self, db_event, fb_event):
        self.db_event = db_event
        self.fb_event = fb_event
        self.start_time = dates.parse_fb_timestamp(self.fb_event['info'].get('start_time'))
        self.end_time = dates.parse_fb_timestamp(self.fb_event['info'].get('end_time'))
        self.rsvp_status = "unknown"
        self.event_types = ', '.join(self.db_event.event_keywords or [])
        self.attending_friend_count = 0
        self.attending_friends = []

        self.index = None

    def multi_day_event(self):
        return (self.end_time - self.start_time) > datetime.timedelta(hours=24)

    def get_image(self):
        picture_url = self.fb_event.get('picture')
        if picture_url:
            return eventdata.get_event_image_url(picture_url, eventdata.EVENT_IMAGE_LARGE)
        else:
            logging.error("Error loading picture for event id %s", self.fb_event['info']['id'])
            logging.error("Data is %s\n\n%s", self.db_event, self.fb_event)
            return 'http://graph.facebook.com/%s/picture?type=large' % self.fb_event['info']['id']

    def get_attendance(self):
        if self.rsvp_status == 'unsure':
            return 'maybe'
        return self.rsvp_status

class SearchQuery(object):
    def __init__(self, time_period=None, start_time=None, end_time=None, bounds=None, min_attendees=None):
        self.time_period = time_period

        self.min_attendees = min_attendees
        self.start_time = start_time
        self.end_time = end_time
        if self.start_time and self.end_time:
            assert self.start_time < self.end_time
        if self.time_period == eventdata.TIME_FUTURE and self.end_time:
                assert self.end_time > datetime.datetime.now()
        if self.time_period == eventdata.TIME_FUTURE and self.start_time:
                assert self.start_time < datetime.datetime.now()
        self.bounds = bounds
        assert self.bounds

        self.search_geohashes = locations.get_all_geohashes_for(bounds)
        logging.info("Searching geohashes %s", self.search_geohashes)

    def matches_db_event(self, event):
        if self.start_time:
            if self.start_time < event.end_time:
                pass
            else:
                return False
        if self.end_time:
            if event.start_time < self.end_time:
                pass
            else:
                return False

        if self.min_attendees and event.attendee_count < self.min_attendees:
            return False

        if not locations.contains(self.bounds, (event.latitude, event.longitude)):
            return False

        return True

    def matches_fb_db_event(self, event, fb_event):
        return True
    
    def get_candidate_events(self):
        clauses = []
        bind_vars = {}
        if self.search_geohashes:
            clauses.append('geohashes in :search_geohashes')
            bind_vars['search_geohashes'] = self.search_geohashes
        if self.time_period:
            clauses.append('search_time_period = :search_time_period')
            bind_vars['search_time_period'] = self.time_period
        if self.start_time: # APPROXIMATION
            clauses.append('start_time > :start_time_min')
            bind_vars['start_time_min'] = self.start_time - datetime.timedelta(days=30)
        if self.end_time:
            clauses.append('start_time < :start_time_max')
            bind_vars['start_time_max'] = self.end_time
        if clauses:
            full_clauses = ' AND '.join('%s' % x for x in clauses)
            logging.info("Doing search with clauses: %s", full_clauses)
            return eventdata.DBEvent.gql('WHERE %s' % full_clauses, **bind_vars).fetch(1000)
        else:
            return eventdata.DBEvent.all().fetch(1000)

    def magical_get_candidate_events(self):
        a = time.time()
        search_events = get_search_index()
        event_ids = []
        for fb_event_id, (latitude, longitude) in search_events:
            if locations.contains(self.bounds, (latitude, longitude)):
                event_ids.append(fb_event_id)
        logging.info("loading and filtering search index took %s seconds", time.time() - a)
        db_events = eventdata.get_cached_db_events(event_ids)
        return db_events

    def get_search_results(self, fb_uid, graph):
        db_events = None
        if self.time_period == eventdata.TIME_FUTURE:
            # Use cached blob for our common case of filtering
            db_events = self.magical_get_candidate_events()
        if db_events is None:
            # Do datastore filtering
            db_events = self.get_candidate_events()

        orig_db_events_length = len(db_events)
        # Do some obvious filtering before loading the fb events for each.
        db_events = [x for x in db_events if self.matches_db_event(x)]
        logging.info("in-process filtering trimmed us from %s to % events", orig_db_events_length, len(db_events))

        # Now look up contents of each event...
        a = time.time()
        batch_lookup = fb_api.CommonBatchLookup(fb_uid, graph)
        for db_event in db_events:
            batch_lookup.lookup_event(db_event.fb_event_id)
        batch_lookup.finish_loading()
        logging.info("loading fb data took %s seconds", time.time() - a)

        # ...and do filtering based on the contents inside our app
        a = time.time()
        search_results = []
        for db_event in db_events:
            fb_event = batch_lookup.data_for_event(db_event.fb_event_id)
            if not fb_event['deleted'] and self.matches_fb_db_event(db_event, fb_event):
                result = SearchResult(db_event, fb_event)
                search_results.append(result)
        logging.info("db filtering and Search Results took %s seconds", time.time() - a)
    
        # Now sort and return the results
        a = time.time()
        search_results.sort(key=lambda x: x.fb_event['info'].get('start_time'))
        logging.info("search result sorting took %s seconds", time.time() - a)
        return search_results

def construct_search_index():
    MAX_EVENTS = 5000
    db_events = db.Query(eventdata.DBEvent).filter('search_time_period =', eventdata.TIME_FUTURE).order('start_time').fetch(MAX_EVENTS)
    eventdata.cache_db_events(db_events)
    if len(db_events) >= MAX_EVENTS:
        slogging.error('Found %s future events. Increase the MAX_EVENTS limit to search more events.', MAX_EVENTS)

    search_events = [(x.fb_event_id, (x.latitude, x.longitude)) for x in db_events if x.latitude or x.longitude]
    return search_events

SEARCH_INDEX_MEMCACHE_KEY = 'SearchIndex'

def get_search_index(allow_cache=True):
    search_index = None
    if allow_cache:
        search_index = smemcache.get(SEARCH_INDEX_MEMCACHE_KEY)
    if not search_index:
        search_index = construct_search_index()
        smemcache.set(SEARCH_INDEX_MEMCACHE_KEY, search_index, time=2*3600)
    return search_index

# since _inner_cache_fb_events is a decorated function, it can't be pickled, which breaks deferred. so make this wrapper function here.
def cache_fb_events(batch_lookup, search_index):
    _inner_cache_fb_events(batch_lookup, search_index)

EVENTS_AT_A_TIME = 200
@timings.timed
def _inner_cache_fb_events(batch_lookup, search_index):
    """Load and stick fb events into cache."""
    if len(search_index) > EVENTS_AT_A_TIME:
        deferred.defer(cache_fb_events, batch_lookup, search_index[EVENTS_AT_A_TIME:], _queue=SLOW_QUEUE)
        search_index = search_index[:EVENTS_AT_A_TIME]
    batch_lookup = batch_lookup.copy()
    batch_lookup.allow_memcache = False
    for event_id, latlng in search_index:
        batch_lookup.lookup_event(event_id)
        batch_lookup.lookup_event_attending(event_id)
    logging.info("Loading %s events into memcache", len(search_index))
    batch_lookup.finish_loading()

@timings.timed
def recache_everything(batch_lookup):
    search_index = get_search_index(allow_cache=False)
    logging.info("Overall loading %s events into memcache", len(search_index))
    deferred.defer(cache_fb_events, batch_lookup, search_index, _queue=SLOW_QUEUE)
    # caching of db events is done automatically by construct_search_index since it already has the db events loaded
