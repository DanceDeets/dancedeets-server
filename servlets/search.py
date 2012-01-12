#!/usr/bin/env python

import datetime
import logging
import time
import urllib

import base_servlet
from events import cities
from events import eventdata
from events import users
from logic import rankings
from logic import friends
from logic import rsvp
from logic import search
import fb_api
import locations
from util import timings

class RelevantHandler(base_servlet.BaseRequestHandler):
    def requires_login(self):
        if not self.request.get('location') and not self.request.get('city_name'):
            return True
        return False

    def get(self):
        self.handle()

    def post(self):
        self.handle()

    @timings.timed
    def handle(self, city_name=None):
        self.finish_preload()
        if self.user and not self.user.location:
            #TODO(lambert): make this an error
            self.user.add_message("We could not retrieve your location from facebook. Please fill out a location below")
            self.redirect('/user/edit')
            return

        fe_search_query = search.FrontendSearchQuery()

        # in case we get it passed in via the URL handler
        city_name = city_name or self.request.get('city_name')

        if city_name:
            fe_search_query.location = city_name
            fe_search_query.distance = 50
            fe_search_query.distance_units = 'miles'
        else:
            fe_search_query.location = self.request.get('location', self.user and self.user.location)
            fe_search_query.distance = int(self.request.get('distance', self.user and self.user.distance or 50))
            fe_search_query.distance_units = self.request.get('distance_units', self.user and self.user.distance_units or 'miles')

        if fe_search_query.distance_units == 'miles':
            distance_in_km = locations.miles_in_km(fe_search_query.distance)
        else:
            distance_in_km = fe_search_query.distance
        bounds = locations.get_location_bounds(fe_search_query.location, distance_in_km)
        fe_search_query.past = self.request.get('past', '0') not in ['0', '', 'False', 'false']


        fe_search_query.min_attendees = int(self.request.get('min_attendees', self.user and self.user.min_attendees or 0))

        if fe_search_query.past:
            time_period = eventdata.TIME_PAST
        else:
            time_period = eventdata.TIME_FUTURE

        if not self.request.get('calendar'):
            query = search.SearchQuery(time_period=time_period, bounds=bounds, min_attendees=fe_search_query.min_attendees)
            search_results = query.get_search_results(self.fb_uid, self.fb_graph)
            # We can probably speed this up 2x by shrinking the size of the fb-event-attending objects. a list of {u'id': u'100001860311009', u'name': u'Dance InMinistry', u'rsvp_status': u'attending'} is 50% overkill.
            a = time.time()
            friends.decorate_with_friends(self.batch_lookup, search_results)
            logging.info("Decorating with friends-attending took %s seconds", time.time() - a)
            a = time.time()
            rsvp.decorate_with_rsvps(self.batch_lookup, search_results)
            logging.info("Decorating with personal rsvp data took %s seconds", time.time() - a)

            past_results, present_results, grouped_results = search.group_results(search_results)
            if time_period == eventdata.TIME_FUTURE:
                present_results = past_results + present_results
                past_results = []

            self.display['num_upcoming_results'] = sum([len(x.results) for x in grouped_results]) + len(present_results)
            self.display['past_results'] = past_results
            self.display['ongoing_results'] = present_results
            self.display['grouped_upcoming_results'] = grouped_results

        if fe_search_query.past:
                self.display['selected_tab'] = 'past'
        elif self.request.get('calendar'):
            self.display['selected_tab'] = 'calendar'
        else:
            self.display['selected_tab'] = 'present'

        a = time.time()
        closest_cityname = cities.get_largest_nearby_city_name(fe_search_query.location)
        logging.info("computing largest nearby city took %s seconds", time.time() - a)

        a = time.time()
        #TODO(lambert): perhaps produce optimized versions of these without styles/times, for use on the homepage? less pickling/loading required
        event_top_n_cities, event_selected_n_cities = rankings.top_n_with_selected(rankings.get_thing_ranking(rankings.get_city_by_event_rankings(), rankings.ALL_TIME), closest_cityname)
        user_top_n_cities, user_selected_n_cities = rankings.top_n_with_selected(rankings.get_thing_ranking(rankings.get_city_by_user_rankings(), rankings.ALL_TIME), closest_cityname)
        logging.info("Sorting and ranking top-N cities took %s seconds", time.time() - a)

        self.display['current_city'] = closest_cityname
        self.display['user_top_n_cities'] = user_top_n_cities
        self.display['event_top_n_cities'] = event_top_n_cities
        self.display['user_selected_n_cities'] = user_selected_n_cities
        self.display['event_selected_n_cities'] = event_selected_n_cities

        self.display['defaults'] = fe_search_query
        self.display['display_location'] = fe_search_query.location

        request_params = fe_search_query.url_params()
        if 'calendar' in request_params:
            del request_params['calendar'] #TODO(lambert): clean this up more
        if 'past' in request_params:
            del request_params['past'] #TODO(lambert): clean this up more
        self.display['past_view_url'] = '/events/relevant?past=1&%s' % '&'.join('%s=%s' % (k, v) for (k, v) in request_params.iteritems())
        self.display['upcoming_view_url'] = '/events/relevant?%s' % '&'.join('%s=%s' % (k, v) for (k, v) in request_params.iteritems())
        self.display['calendar_view_url'] = '/events/relevant?calendar=1&%s' % '&'.join('%s=%s' % (k, v) for (k, v) in request_params.iteritems())
        self.display['calendar_feed_url'] = '/calendar/feed?%s' % '&'.join('%s=%s' % (k, v) for (k, v) in request_params.iteritems())

        self.display['CHOOSE_RSVPS'] = eventdata.CHOOSE_RSVPS
        self.render_template('results')

class CityHandler(RelevantHandler):
    def requires_login(self):
        return False

    def handle(self):
        path_bits = self.request.path.split('/')
        city_name = urllib.unquote(path_bits[2])

        # if they only care about particular types, too bad, redirect them to the main page since we don't support that anymore
        if len(path_bits) >= 4:
            self.redirect('/'.join(path_bits[:-1]))
            return

        super(CityHandler, self).handle(city_name=city_name)
