import logging

from google.appengine.ext import deferred

import fb_api
from events import eventdata
from events import event_locations
from events import event_updates
from pubsub import pubsub
from nlp import event_classifier
from . import potential_events
from . import thing_db

class AddEventException(Exception):
    pass

def add_update_event(fb_event, fbl, creating_uid=None, visible_to_fb_uids=None, remapped_address=None, override_address=None, creating_method=None):
    if not fb_api.is_public_ish(fb_event):
        raise AddEventException('Cannot add secret/closed events to dancedeets!')

    if remapped_address is not None:
        event_locations.update_remapped_address(fb_event, remapped_address)

    e = eventdata.DBEvent.get_or_insert(fb_event['info']['id'])
    newly_created = (e.creating_fb_uid is None)
    if override_address is not None:
        e.address = override_address
    #STR_ID_MIGRATE
    e.creating_fb_uid = long(creating_uid) if creating_uid else None
    if creating_method:
        e.creating_method = creating_method

    if visible_to_fb_uids is None:
        if creating_uid is not None:
            visible_to_fb_uids = [creating_uid]
        else:
            visible_to_fb_uids = []
    e.visible_to_fb_uids = visible_to_fb_uids

    event_updates.update_and_save_events([(e, fb_event)])
    thing_db.create_source_from_event(fbl, e)

    if newly_created:
        logging.info("New event, publishing to twitter/facebook")
        deferred.defer(pubsub.eventually_publish_event, e.fb_event_id)

    #DISABLE_ATTENDING
    fb_event_attending = None
    potential_event = potential_events.make_potential_event_without_source(e.fb_event_id, fb_event, fb_event_attending)
    classified_event = event_classifier.get_classified_event(fb_event, potential_event.language)
    if potential_event:
        for source_id in potential_event.source_ids:
            #STR_ID_MIGRATE
            source_id = str(source_id)
            thing_db.increment_num_real_events(source_id)
            if not classified_event.is_dance_event():
                thing_db.increment_num_false_negatives(source_id)
    # Hmm, how do we implement this one?# thing_db.increment_num_real_events_without_potential_events(source_id)
