import datetime
import json
import logging

from google.appengine.ext import db
from mapreduce import json_util
from mapreduce import mapreduce_pipeline
from mapreduce import operation

from events import eventdata
import fb_api
from loc import gmaps_api
from util import fb_mapreduce

GRAPH_TYPE_PROFILE = 'GRAPH_TYPE_PROFILE'
GRAPH_TYPE_FANPAGE = 'GRAPH_TYPE_FANPAGE'
GRAPH_TYPE_EVENT = 'GRAPH_TYPE_EVENT'
GRAPH_TYPE_GROUP = 'GRAPH_TYPE_GROUP'

GRAPH_TYPES = [
    GRAPH_TYPE_PROFILE,
    GRAPH_TYPE_FANPAGE,
    GRAPH_TYPE_EVENT,
    GRAPH_TYPE_GROUP,
]

# Start small
# Only set of sources with walls, and only hand-curated sources (or events). not grabbing new peoples yet.

FIELD_FEED = 'FIELD_FEED' # /feed
FIELD_EVENTS = 'FIELD_EVENTS' # /events
FIELD_INVITES = 'FIELD_INVITES' # fql query on invites for signed-up users

class Source(db.Model):
    graph_id = property(lambda x: str(x.key().name()))
    graph_type = db.StringProperty(choices=GRAPH_TYPES)

    # cached/derived from fb data
    name = db.StringProperty(indexed=False)
    feed_history_in_seconds = db.IntegerProperty(indexed=False)

    fb_info = json_util.JsonProperty(dict, indexed=False)
    latitude = db.FloatProperty(indexed=False)
    longitude = db.FloatProperty(indexed=False)

    street_dance_related = db.BooleanProperty()

    # probably to assume for a given event? rough weighting factor?
    # do we want to delete these now?
    freestyle = db.FloatProperty(indexed=False)
    choreo = db.FloatProperty(indexed=False)

    #STR_ID_MIGRATE
    creating_fb_uid = db.IntegerProperty(indexed=False)
    creation_time = db.DateTimeProperty(indexed=False, auto_now_add=True)
    last_scrape_time = db.DateTimeProperty(indexed=False)

    num_all_events = db.IntegerProperty(indexed=False)
    num_potential_events = db.IntegerProperty(indexed=False)
    num_real_events = db.IntegerProperty(indexed=False)
    num_false_negatives = db.IntegerProperty(indexed=False)

    def fraction_potential_are_real(self, bias=1):
        num_real_events = (self.num_real_events or 0) + bias
        num_potential_events = (self.num_potential_events or 0) + bias
        if num_potential_events:
            return 1.0 * num_real_events / num_potential_events
        else:
            return 0

    def fraction_real_are_false_negative(self, bias=1):
        if self.num_real_events:
            #TODO(lambert): figure out why num_false_negatives is None, in particular for source id=107687589275667 even after saving
            num_false_negatives = (self.num_false_negatives or 0) + bias
            num_real_events = (self.num_real_events or 0) + bias
            return 1.0 * num_false_negatives / num_real_events
        else:
            return 0

    def compute_derived_properties(self, fb_data):
        if fb_data:
            if fb_data['empty']: # only update these when we have feed data
                self.fb_info = {}
            else:
                self.fb_info = fb_data['info']
                if 'likes' in fb_data['info']:
                    self.graph_type = GRAPH_TYPE_FANPAGE
                elif 'locale' in fb_data['info'] or 'first_name' in fb_data['info']:
                    self.graph_type = GRAPH_TYPE_PROFILE
                elif 'groups.facebook.com' in fb_data['info'].get('email', []):
                    self.graph_type = GRAPH_TYPE_GROUP
                elif 'start_time' in fb_data['info']:
                    self.graph_type = GRAPH_TYPE_EVENT
                else:
                    logging.info("cannot classify object type for id %s", fb_data['info']['id'])
                if 'name' not in fb_data['info']:
                    logging.error('cannot find name for fb event data: %s, cannot update source data...', fb_data)
                    return
                self.name = fb_data['info']['name']
                feed = fb_data['feed']['data']
                if len(feed):
                    dt = datetime.datetime.strptime(feed[-1]['created_time'], '%Y-%m-%dT%H:%M:%S+0000')
                    td = datetime.datetime.now() - dt
                    total_seconds = td.seconds + td.days * 24 * 3600
                    self.feed_history_in_seconds = total_seconds
                    #logging.info('feed time delta is %s', self.feed_history_in_seconds)
                else:
                    self.feed_history_in_seconds = 0
                location = fb_data['info'].get('location')
                if location:
                    if location.get('latitude'):
                        self.latitude = float(location.get('latitude'))
                        self.longitude = float(location.get('longitude'))
                    else:
                        component_names = ['street', 'city', 'state', 'zip', 'region', 'country']
                        components = [location.get(x) for x in component_names if location.get(x)]
                        address = ', '.join(components)
                        geocode = gmaps_api.lookup_address(address)
                        if geocode:
                            self.latitude, self.longitude = geocode.latlng()
        #TODO(lambert): at some point we need to calculate all potential events, and all real events, and update the numbers with values from them. and all fake events. we have a problem where a new source gets added, adds in the potential events and/or real events, but doesn't properly tally them all. can fix this one-off, but it's too-late now, and i imagine our data will grow inaccurate over time anyway.

def link_for_fb_source(data):
    if 'link' in data['info']:
        return data['info']['link']
    elif 'version' in data['info']:
        return 'http://www.facebook.com/groups/%s/' % data['info']['id']
    elif 'start_time' in data['info']:
        return 'http://www.facebook.com/events/%s/' % data['info']['id']
    else:
        return 'http://www.facebook.com/%s/' % data['info']['id']

def create_source_for_id(source_id, fb_data):
    source = Source.get_by_key_name(source_id) or Source(key_name=source_id, street_dance_related=False)
    source.compute_derived_properties(fb_data)
    logging.info('Getting source for id %s: %s', source.graph_id, source.name)
    return source

def create_source_from_event(fbl, db_event):
    if not db_event.owner_fb_uid:
        return
    # technically we could check if the object exists in the db, before we bother fetching the feed
    thing_feed = fbl.get(fb_api.LookupThingFeed, db_event.owner_fb_uid)
    if not thing_feed['empty']:
        s = create_source_for_id(db_event.owner_fb_uid, thing_feed)
        s.put()
map_create_source_from_event = fb_mapreduce.mr_wrap(create_source_from_event)

def export_sources(fbl, sources):
    fbl.request_multi(fb_api.LookupThingFeed, [x.graph_id for x in sources])
    fbl.batch_fetch()
    for source in sources:
        try:
            thing_feed = fbl.fetched_data(fb_api.LookupThingFeed, source.graph_id)
            if 'info' not in thing_feed:
                continue
            name = thing_feed['info'].get('name', '').encode('utf8')
            desc = thing_feed['info'].get('description', '').encode('utf8')
            fields = (
                source.graph_id,
                source.graph_type,
                source.creation_time,
                source.creating_fb_uid,
                source.feed_history_in_seconds,
                source.last_scrape_time,
                source.num_all_events,
                source.num_false_negatives,
                source.num_potential_events,
                source.num_real_events,
                name.replace('\n', ' ').replace('\t', ' '),
                desc.replace('\n', ' ').replace('\t', ' '),
                )
            yield '%s\n' % '\t'.join([str(x) for x in fields])
        except fb_api.NoFetchedDataException, e:
            logging.warning("Failed to fetch data for thing: %s", str(e))
map_export_sources = fb_mapreduce.mr_wrap(export_sources)

def mapreduce_export_sources(fbl, queue='fast-queue'):
    fb_mapreduce.start_map(
        fbl,
        'Export All Sources',
        'event_scraper.thing_db.map_export_sources',
        'event_scraper.thing_db.Source',
        output_writer_spec='mapreduce.output_writers.GoogleCloudStorageOutputWriter',
        output_writer={
            'mime_type': 'text/plain',
            'bucket_name': 'dancedeets-hrd.appspot.com',
        },
        handle_batch_size=10,
        queue=queue,
    )


def explode_per_source_count(pe):
    db_event = eventdata.DBEvent.get_by_id(pe.fb_event_id)

    is_potential_event = pe.match_score > 0
    real_event = db_event != None
    false_negative = bool(db_event and not is_potential_event)
    result = (is_potential_event, real_event, false_negative)

    for source_id in pe.source_ids:
        #STR_ID_MIGRATE
        source_id = str(source_id)
        yield (source_id, json.dumps(result))

def combine_source_count(source_id, counts_to_sum):
    s = Source.get_by_key_name(source_id)
    if not s:
        return

    s.num_all_events = 0
    s.num_potential_events = 0
    s.num_real_events = 0
    s.num_false_negatives = 0

    for result in counts_to_sum:
        (potential_event, real_event, false_negative) = json.loads(result)
        s.num_all_events += 1
        if potential_event:
            s.num_potential_events += 1
        if real_event:
            s.num_real_events += 1
        if false_negative:
            s.num_false_negatives += 1
    yield operation.db.Put(s)

def mr_count_potential_events(fbl, queue):
    mapper_params = {
        'entity_kind': 'event_scraper.potential_events.PotentialEvent',
    }
    mapper_params.update(fb_mapreduce.get_fblookup_params(fbl))
    pipeline = mapreduce_pipeline.MapreducePipeline(
        'clean source counts',
        'event_scraper.thing_db.explode_per_source_count',
        'event_scraper.thing_db.combine_source_count',
        'mapreduce.input_readers.DatastoreInputReader',
        None,
        mapper_params=mapper_params,
    )
    pipeline.start(queue_name=queue)

"""
user:
- invited-events fql (event, if member)
- friends (user, if member)
- events (event)
- wall (event, user, page, group)
- likes (page)
- groups (group)

fanpage:
- wall (event, user, page, group)
- likes (page)
- events (event)
- groups (group)

event:
- wall (event, user, page, group)
- attending (user)
- creator (user)

group:
- wall (event, user, page, group)
- members (user)

Known Dancer Entities (profiles, fan pages, events, groups)
- scrape them for events
- track in each entity, how many events were found on wall, events
- track total-time-of-wall so we know refresh frequency

status:
dance-related, scrape, add everything in here to "maybe" list
maybe-dance-related, scrape but only return high-quality events, don't scrape for anything-but-events
not-dance-related, don't scrape
old (event), no longer scrape, happens after event has passed

status set periodically in all-out-mapreduce
- old events stay old
- sources stay dance-related if manually set
- sources become dance-related if they find dance events via it
- sources become not-dance-related if there are no dance events on it after a month or two? or if number of dancer-friends is <20?

- also want to track how many pages/groups were found via this entity
"""
