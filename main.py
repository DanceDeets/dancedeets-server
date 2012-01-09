#!/usr/bin/env python

import logging
import os
import wsgiref.handlers
import yaml
from google.appengine.ext import webapp
from google.appengine.ext import ereporter
from google.appengine.ext.webapp.util import run_wsgi_app
import base_servlet
from servlets import about
from servlets import admin
from servlets import atom
from servlets import calendar
from servlets import event
from servlets import feedback
from servlets import login
from servlets import myuser
from servlets import profile_page
from servlets import search
from servlets import share
from servlets import source
from servlets import stats
from servlets import tasks
from servlets import tools
from servlets import youtube_simple_api
import smemcache

class DoNothingHandler(base_servlet.BareBaseRequestHandler):
    def get(self):
        return

URLS = [
    ('/tools/owned_events', tools.OwnedEventsHandler),
    ('/tools/unprocess_future_events', tools.UnprocessFutureEventsHandler),
    ('/tools/oneoff', tools.OneOffHandler),
    ('/tools/import_cities', tools.ImportCitiesHandler),
    ('/tools/migrate_dbevents', tools.MigrateDBEventsHandler),
    ('/tools/clear_memcache', admin.ClearMemcacheHandler),
    ('/tools/delete_fb_cache', admin.DeleteFBCacheHandler),
    ('/tools/show_users', admin.ShowUsersHandler),
    ('/tools/fb_data', admin.FBDataHandler),
    ('/tasks/load_events', tasks.LoadEventHandler),
    ('/tasks/load_users', tasks.LoadUserHandler),
    ('/tasks/load_event_attending', tasks.LoadEventAttendingHandler),
    ('/tasks/track_newuser_friends', tasks.TrackNewUserFriendsHandler),
    ('/tasks/reload_all_users', tasks.ReloadAllUsersHandler),
    ('/tasks/reload_all_events', tasks.ReloadAllEventsHandler),
    ('/tasks/reload_future_events', tasks.ReloadFutureEventsHandler),
    ('/tasks/reload_past_events', tasks.ReloadPastEventsHandler),
    ('/tasks/email_all_users', tasks.EmailAllUsersHandler),
    ('/tasks/email_user', tasks.EmailUserHandler),
    ('/tasks/load_all_potential_events', tasks.LoadAllPotentialEventsHandler),
    ('/tasks/load_potential_events_for_friends', tasks.LoadPotentialEventsForFriendsHandler),
    ('/tasks/load_potential_events_for_user', tasks.LoadPotentialEventsForUserHandler),
    ('/tasks/load_potential_events_from_wall_posts', tasks.LoadPotentialEventsFromWallPostsHandler),
    ('/tasks/compute_rankings', tasks.ComputeRankingsHandler),
    ('/tasks/recache_search_index', tasks.RecacheSearchIndex),
    ('/tasks/timings_keep_alive', tasks.TimingsKeepAlive),
    ('/tasks/timings_process_day', tasks.TimingsProcessDay),
    ('/', search.RelevantHandler),
    ('/_ah/warmup', DoNothingHandler),
    ('/rankings', stats.RankingsHandler),
    ('/events/admin_nolocation_events', event.AdminNoLocationEventsHandler),
    ('/events/admin_potential_events', event.AdminPotentialEventViewHandler),
    ('/events/admin_edit', event.AdminEditHandler),
    ('/events/redirect', event.RedirectToEventHandler),
    ('/events/add', event.AddHandler),
    ('/events/feed', atom.AtomHandler),
    ('/city/.*', search.CityHandler),
    ('/profile/[^/]*', profile_page.ProfileHandler),
    ('/profile/[^/]*/add_tag', profile_page.ProfileAddTagHandler),
    ('/youtube_simple_api', youtube_simple_api.YoutubeSimpleApiHandler),
    ('/calendar', calendar.CalendarHandler),
    ('/calendar/feed', calendar.CalendarFeedHandler),
    ('/sources/admin_edit', source.AdminEditHandler),
    ('/events/relevant', search.RelevantHandler),
    ('/events/rsvp_ajax', event.RsvpAjaxHandler),
    ('/user/edit', myuser.UserHandler),
    ('/login', login.LoginHandler),
    ('/share', share.ShareHandler),
    ('/about', about.AboutHandler),
    ('/help', feedback.HelpHandler),
    ('/feedback', feedback.FeedbackHandler),
]

class MyWSGIApplication(webapp.WSGIApplication):
    def __init__(self, url_mapping, debug=False, prod_mode=False):
        self.debug = debug
        self.prod_mode = prod_mode
        super(MyWSGIApplication, self).__init__(url_mapping)

    def __call__(self, environ, start_response):
        """Called by WSGI when a request comes in."""
        request = self.REQUEST_CLASS(environ)
        response = self.RESPONSE_CLASS()

        webapp.WSGIApplication.active_instance = self

        processed = False
        handler = None
        groups = ()
        for regexp, handler_class in self._url_mapping:
            match = regexp.match(request.path)
            if match:
                handler = handler_class()
                handler.prod_mode = self.prod_mode # since we can't change the __init__ or intialize APIs, we must do this here
                processed = handler.initialize(request, response)
                groups = match.groups()
                break

        self.current_request_args = groups

        if not processed:
            if handler:
                try:
                    method = environ['REQUEST_METHOD']
                    if method == 'GET':
                        handler.get(*groups)
                    elif method == 'POST':
                        handler.post(*groups)
                    elif method == 'HEAD':
                        handler.head(*groups)
                    elif method == 'OPTIONS':
                        handler.options(*groups)
                    elif method == 'PUT':
                        handler.put(*groups)
                    elif method == 'DELETE':
                        handler.delete(*groups)
                    elif method == 'TRACE':
                        handler.trace(*groups)
                    else:
                        handler.error(501)
                except Exception, e:
                    handler.handle_exception(e, self.debug)
            else:
                response.set_status(404)

        response.wsgi_write(start_response)
        return ['']

def get_application(prod_mode=False):
    if prod_mode:
        filename = 'facebook-prod.yaml'
    else:
        filename = 'facebook.yaml'
    base_servlet.FACEBOOK_CONFIG = yaml.load(file(filename, 'r'))
     application = MyWSGIApplication(URLS, debug=True, prod_mode=prod_mode)
    return application

def main():
    ereporter.register_logger()
    prod_mode = not os.environ['SERVER_SOFTWARE'].startswith('Dev')
    run_wsgi_app(get_application(prod_mode))


if __name__ == '__main__':
    main()
