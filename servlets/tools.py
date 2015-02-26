#Leaving these in-but-commented-out for future ease-of-hacking:
import logging
#import time
import webapp2
from google.appengine.api import memcache
#from google.appengine.ext import db
#from google.appengine.ext import deferred

from mapreduce import context
#from mapreduce import control
from mapreduce import operation as op
#from mapreduce import util

import base_servlet
from events import cities
from events import eventdata
from events import users
import fb_api
from logic import auto_add
#from logic import mr_dump
#from logic import mr_prediction
#from logic import potential_events
from logic import thing_db
#from nlp import event_classifier


class UnprocessFutureEventsHandler(webapp2.RequestHandler):
    def get(self):
        #TODO(lambert): reimplement if needed:
        #if entity.key().name().endswith('OBJ_EVENT'):
        #    if entity.json_data:
        #        event = entity.decode_data()
        #        if not event['empty']:
        #            info = event['info']
        #            if info.get('start_time') > '2011-04-05' and info['updated_time'] > '2011-04-05':
        #                pe = potential_events.PotentialEvent.get_or_insert(event['info']['id'])
        #                pe.looked_at = None
        #                pe.put()
        #                logging.info("PE %s", event['info']['id'])
        return

def map_delete_cached_with_wrong_user_id(fbo):
    user_id, obj_id, obj_type = fbo.key().name().split('.')
    bl = fb_api.BatchLookup
    bl_types = (bl.OBJECT_EVENT, bl.OBJECT_EVENT_ATTENDING, bl.OBJECT_EVENT_MEMBERS, bl.OBJECT_THING_FEED, bl.OBJECT_VENUE)
    if obj_type in bl_types and user_id != '701004':
        yield op.db.Delete(fbo)


def count_private_events(fbl, e_list):
    fbl.get(fb_api.LookupEvent, [x.fb_event_id for x in e_list])
    fbl.batch_fetch()

    ctx = context.get()

    for e in e_list:
        try:
            fbe = fbl.fetched_data(fb_api.LookupEvent, e.fb_event_id)
            if 'info' not in fbe:
                logging.error("skipping row2 for event id %s", e.fb_event_id)
                continue
            attendees = fb_api._all_members_count(fbe)
            privacy = fbe['info'].get('privacy', 'OPEN')
            if privacy != 'OPEN' and attendees > 60:
                ctx.counters.increment('nonpublic-and-large')
            ctx.counters.increment('privacy-%s' % privacy)

            yield e.fb_event_id, privacy, attendees
        except fb_api.NoFetchedDataException:
            logging.error("skipping row for event id %s", e.fb_event_id)

from util import fb_mapreduce
map_dump_private_events = fb_mapreduce.mr_wrap(count_private_events)

def mr_private_events(fbl):
    fb_mapreduce.start_map(
        fbl,
        'Dump Private Events',
        'servlets.tools.map_dump_private_events',
        'events.eventdata.DBEvent',
        handle_batch_size=80,
        queue=None,
        filters=[('search_time_period', '=', eventdata.TIME_FUTURE)],
        output_writer_spec='mapreduce.output_writers.GoogleCloudStorageOutputWriter',
        output_writer={
            'mime_type': 'text/plain',
            'bucket_name': 'dancedeets-hrd.appspot.com',
        },
    )

#base_servlet.BaseTaskFacebookRequestHandler):#
class OneOffHandler(webapp2.RequestHandler):
    def get(self):
        from logic import thing_scraper
        thing_scraper.mr_delete_bad_sources()

class AutoAddPotentialEventsHandler(base_servlet.BaseTaskFacebookRequestHandler):
    def get(self):
        past_event = self.request.get('past_event', None)
        if past_event == '1':
            past_event = True
        elif past_event == '0':
            past_event = False
        auto_add.mr_classify_potential_events(self.fbl, past_event)

class ExportSourcesHandler(base_servlet.BaseTaskFacebookRequestHandler):
    def get(self):
        queue = self.request.get('queue', 'fast-queue')
        thing_db.mapreduce_export_sources(self.fbl, queue=queue)

class OwnedEventsHandler(webapp2.RequestHandler):
    def get(self):
        db_events_query = eventdata.DBEvent.query(eventdata.DBEvent.owner_fb_uid==self.request.get('owner_id'))
        db_events = db_events_query.fetch(1000)

        print 'Content-type: text/plain\n\n'
        keys = [fb_api.generate_key(fb_api.LookupEvent, x.fb_event_id) for x in db_events]
        fb_events = fb_api.DBCache(None).fetch_keys(keys)
        for db_event, fb_event in zip(db_events, fb_events):
            real_fb_event = fb_event.decode_data()
            print db_event.tags, real_fb_event['info']['name']

class ImportCitiesHandler(webapp2.RequestHandler):
    def get(self):
        cities.import_cities()
        self.response.out.write("Imported Cities!")

class ClearMemcacheHandler(webapp2.RequestHandler):
    def get(self):
        memcache.flush_all()
        self.response.out.write("Flushed memcache!")


