import logging

from google.appengine.ext import db
from google.appengine.runtime import apiproxy_errors

from logic import gtranslate
from nlp import event_classifier
from util import dates
from . import thing_db

class DiscoveredEvent(object):
    def __init__(self, fb_event_id, source, source_field, extra_source_id=None):
        self.event_id = fb_event_id
        # still necessary for fraction_are_real_event checks...can we remove dependency?
        self.source = source
        self.source_id = source.graph_id if source else None
        self.source_field = source_field
        self.extra_source_id = extra_source_id

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, ', '.join('%s=%s' % x for x in self.__dict__.iteritems()))

    def _repr(self):
        return (self.event_id, self.source_id, self.source_field, self.extra_source_id)

    def __hash__(self):
        return hash(self._repr())

    def __cmp__(self, other):
        if isinstance(other, DiscoveredEvent):
            return cmp(self._repr(), other._repr())
        else:
            return -1

class PotentialEvent(db.Model):
    fb_event_id = property(lambda x: str(x.key().name()))

    language = db.StringProperty(indexed=False)
    looked_at = db.BooleanProperty()
    auto_looked_at = db.BooleanProperty(indexed=False)
    dance_bias_score = db.FloatProperty(indexed=False)
    non_dance_bias_score = db.FloatProperty(indexed=False)
    match_score = db.IntegerProperty()
    show_even_if_no_score = db.BooleanProperty()
    should_look_at = db.BooleanProperty()

    #STR_ID_MIGRATE
    source_ids = db.ListProperty(int)
    source_fields = db.ListProperty(str, indexed=False)

    # This is a representation of FUTURE vs PAST, so we can filter in our mapreduce criteria for relevant future events easily
    past_event = db.BooleanProperty()

    def get_invite_uids(self):
        #STR_ID_MIGRATE
        source_ids = [str(source_id) for source_id, source_field in zip(self.source_ids, self.source_fields) if source_field == thing_db.FIELD_INVITES]
        return source_ids

    def has_discovered(self, discovered_event):
        return self.has_source_with_field(discovered_event.source_id, discovered_event.source_field)

    def has_source_with_field(self, source_id, source_field):
        has_source = False
        for source_id_, source_field_ in zip(self.source_ids, self.source_fields):
            #STR_ID_MIGRATE
            source_id_ = str(source_id_)
            if source_id_ == source_id and source_field_ == source_field:
                has_source = True
        return has_source

    def put(self):
        #TODO(lambert): write as pre-put hook once we're using NDB.
        self.should_look_at = bool(self.match_score > 0 or self.show_even_if_no_score)
        super(PotentialEvent, self).put()

    def set_past_event(self, fb_event):
        if not fb_event:
            past_event = True
        elif fb_event['empty']:
            past_event = True
        else:
            start_time = dates.parse_fb_start_time(fb_event)
            end_time = dates.parse_fb_end_time(fb_event)
            past_event = (dates.TIME_PAST == dates.event_time_period(start_time, end_time))
        changed = (self.past_event != past_event)
        self.past_event = past_event
        return changed


def get_language_for_fb_event(fb_event):
    return gtranslate.check_language('%s. %s' % (
        fb_event['info'].get('name', ''),
        fb_event['info'].get('description', '')
    ))

def _common_potential_event_setup(potential_event, fb_event):
    # only calculate the event score if we've got some new data (new source, etc)
    # TODO(lambert): implement a mapreduce over future-event potential-events that recalculates scores
    # Turn off translation and prediction since they're too expensive for me. :(
    #if not potential_event.language:
    #    potential_event.language = get_language_for_fb_event(fb_event)
    match_score = event_classifier.get_classified_event(fb_event, language=potential_event.language).match_score()
    potential_event.match_score = match_score
    potential_event.set_past_event(fb_event)

def update_scores_for_potential_event(potential_event, fb_event, fb_event_attending, service=None):
    return potential_event # This prediction isn't really working, so let's turn it off for now
    """
    if potential_event and not getattr(potential_event, 'dance_bias_score'):
        predict_service = service or gprediction.get_predict_service()
        dance_bias_score, non_dance_bias_score = gprediction.predict(potential_event, fb_event, fb_event_attending, service=predict_service)
        fb_event_id = potential_event.fb_event_id
        def _internal_update_scores():
            potential_event = PotentialEvent.get_by_key_name(fb_event_id)
            potential_event.dance_bias_score = dance_bias_score
            potential_event.non_dance_bias_score = non_dance_bias_score
            potential_event.put()
            return potential_event
        try:
            potential_event = db.run_in_transaction(_internal_update_scores)
        except apiproxy_errors.CapabilityDisabledError, e:
            logging.error("Error saving potential event %s due to %s", fb_event_id, e)
    return potential_event
    """


def make_potential_event_without_source(fb_event_id, fb_event, fb_event_attending):
    def _internal_add_potential_event():
        potential_event = PotentialEvent.get_by_key_name(fb_event_id)
        if not potential_event:
            potential_event = PotentialEvent(key_name=fb_event_id)
            # TODO(lambert): this may re-duplicate this work for potential events that already exist. is this okay or not?
            _common_potential_event_setup(potential_event, fb_event)
            potential_event.put()
        return potential_event
    try:
        potential_event = db.run_in_transaction(_internal_add_potential_event)
    except apiproxy_errors.CapabilityDisabledError, e:
        logging.error("Error saving potential event %s due to %s", fb_event_id, e)

    # potential_event = update_scores_for_potential_event(potential_event, fb_event, fb_event_attending)
    return potential_event

def make_potential_event_with_source(fb_event, discovered):
    fb_event_id = fb_event['info']['id']
    # show all events from a source if enough of them slip through our automatic filters
    if discovered.source is not None:
        show_all_events = discovered.source.fraction_real_are_false_negative() > 0.05 and discovered.source_field != thing_db.FIELD_INVITES # never show all invites, privacy invasion
    else:
        show_all_events = discovered.source_field != thing_db.FIELD_INVITES
    def _internal_add_source_for_event_id():
        potential_event = PotentialEvent.get_by_key_name(fb_event_id) or PotentialEvent(key_name=fb_event_id)
        # If already added, return
        if potential_event.has_source_with_field(discovered.source_id, discovered.source_field):
            return False, potential_event.match_score

        _common_potential_event_setup(potential_event, fb_event)

        #STR_ID_MIGRATE
        potential_event.source_ids.append(long(discovered.source_id))
        potential_event.source_fields.append(discovered.source_field)

        logging.info('VTFI %s: Just added source id %s to potential event, and saving', fb_event_id, discovered.source_id)

        potential_event.show_even_if_no_score = potential_event.show_even_if_no_score or show_all_events
        potential_event.put()
        return True, potential_event.match_score

    new_source = False
    try:
        new_source, match_score = db.run_in_transaction(_internal_add_source_for_event_id)
    except apiproxy_errors.CapabilityDisabledError, e:
        logging.error("Error saving potential event %s due to %s", fb_event_id, e)
    potential_event = PotentialEvent.get_by_key_name(fb_event_id)
    logging.info('VTFI %s: Just loaded potential event %s, now with sources', fb_event_id, fb_event_id, potential_event.get_invite_uids())

    # potential_event = update_scores_for_potential_event(potential_event, fb_event, fb_event_attending)
    if new_source:
        s = thing_db.Source.get_by_key_name(discovered.source_id)
        #TODO(lambert): doesn't handle the case of the match score increasing from <0 to >0 in the future
        if match_score > 0:
            s.num_potential_events = (s.num_potential_events or 0) + 1
        s.num_all_events = (s.num_all_events or 0) + 1
        s.put()
    return potential_event

