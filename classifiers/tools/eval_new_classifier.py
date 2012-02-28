#!/usr/bin/python

import sys
sys.path += ['.']
from logic import event_classifier
from logic import event_classifier2
from classifiers import processing

ids_info = processing.load_ids()
for x in ids_info:
    print x, len(ids_info[x])
good_ids = ids_info['good_ids']
bad_ids = ids_info['bad_ids']
combined_ids = ids_info['combined_ids']

START_EVENT = 0
END_EVENT = 10000
def partition_ids(classifier=event_classifier.ClassifiedEvent):
    success = set()
    fail = set()
    for i, (id, fb_event) in enumerate(processing.all_fb_data(combined_ids)):
        if not i % 10000: print 'Processing ', i
        if i < START_EVENT:
            continue
        if END_EVENT and i > END_EVENT:
            break
        result = classifier(fb_event)
        result.classify()
        if result.is_dance_event():
            success.add(id)
        else:
            # To print out failures, to see if there's any way we can better detect them
            #if id in good_ids:
            #    print id, fb_event['info'].get('name')
            #    print result.found_dance_matches, result.found_event_matches, result.found_wrong_matches
            fail.add(id)
    return fail, success


print '---'
fail, succeed = partition_ids()
true_positive = succeed.intersection(good_ids)
false_positive = succeed.intersection(bad_ids)
false_negative = fail.intersection(good_ids)
true_negative = fail.intersection(bad_ids)
print 'false negatives', len(false_negative)
print 'true negatives', len(true_negative)

print '--- using old filter ---'
fail2, succeed2 = partition_ids(classifier=event_classifier2.ClassifiedEvent)
true_positive2 = succeed2.intersection(good_ids)
false_positive2 = succeed2.intersection(bad_ids)
false_negative2 = fail2.intersection(good_ids)
true_negative2 = fail2.intersection(bad_ids)
print 'false negatives', len(false_negative2)
print 'true negatives', len(true_negative2)

print '-----'
print "Events we helped find:", len(true_positive.difference(true_positive2))
print "Events we will miss:", len(false_positive.difference(false_positive2))
print "Events we will waste time on:", len(true_negative2.difference(true_negative))

print 'list of used-to-be-positive now-negative dance events (things we will miss)'
for id in false_negative.difference(false_negative2):
    print id
    continue
    fb_event = get_fb_event(id)
    print 'F', id, fb_event['info'].get('owner', {}).get('name'), fb_event['info']['name']
    old = event_classifier.ClassifiedEvent(fb_event).is_dance_event()
    new = event_classifier2.ClassifiedEvent(fb_event).is_dance_event()
    print '  ', old, new

print ''
print ''

print 'list of used-to-be-negative now-positive non-dance events (extra useless work)'
for id in true_negative2.difference(true_negative):
    print id
    continue
    fb_event = get_fb_event(id)
    print 'F', id, fb_event['info'].get('owner', {}).get('name'), fb_event['info']['name']
    old = event_classifier.ClassifiedEvent(fb_event).is_dance_event()
    new = event_classifier2.ClassifiedEvent(fb_event).is_dance_event()
    print '  ', old, new

