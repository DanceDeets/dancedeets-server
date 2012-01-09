# -*-*- encoding: utf-8 -*-*-

import logging
import math
import re
from spitfire.runtime.filters import skip_filter
try:
    from util import timings
    timed = timings.timed
except ImportError:
    timed = lambda x: x

# TODO: translate to english before we try to apply the keyword matches
# TODO: if event creator has created dance events previously, give it some weight
# TODO: 

# TODO: for each style-keyword, give it some weight. don't be a requirement but yet-another-bayes-input
# TODO: add a bunch of classifier logic
# TODO: for iffy events, assume @ in the title means its a club event. same with monday(s) tuesday(s) etc.
# TODO: house class, house workshop, etc, etc. since 'house' by itself isn't sufficient
# maybe feed keywords into auto-classifying event type? bleh.

easy_dance_keywords = [
    'dances?', 'dancing', 'dancers?', 'danser', 'danseur',
    'footwork',
]
easy_choreography_keywords = [
    'choreograph(?:y|ed)', 'choreographers?', 'choreo',
    'koreografi', 'choreografien',

]

dance_and_music_keywords = [
    'hip\W?hop',
    'funk',
    'dance.?hall',
    'ragga',
    'hype',
    'new\W?jack\W?swing',
    'breaks',
    'boogaloo',
    'breaking?', 'breakers?',
    'free\W?style',
    'jerk',
    'kpop',
    'rnb',
    'hard\Whitting',
    'old\W?school hip\W?hop',
    '90\W?s hip\W?hop',
]

# hiphop dance. hiphop dans?
dance_keywords = [
    'breakingu', #breaking polish
    'tanecznych', #dance polish
    'tancerzami', #dancers polish
    'swag',
    'jazz rock',
    'poppers?', 'popp?i?ng?',
    'poppeurs?',
    'commercial hip\W?hop',
    'jerk(?:ers?|ing?)',
    'street\W?dancing?',
    'street\W?dance', 'bre?ak\W?dance', 'bre?ak\W?dancing?', 'brea?ak\W?dancers?',
    'turfing?', 'turf danc\w+', 'flexing?', 'bucking?', 'jooking?',
    'b\W?boy[sz]?', 'b\W?boying?', 'b\W?girl[sz]?', 'b\W?girling?', 'power\W?moves?', 'footworking?',
    'top\W?rock(?:er[sz]?|ing?)?', 'up\W?rock(?:er[sz]?|ing?|)?',
    'houser[sz]?', 'house ?danc\w*',
    'lock(?:er[sz]?|ing?)?', 'lock dance',
    '[uw]h?aa?c?c?ker[sz]?', '[uw]h?aa?cc?kinn?g?', '[uw]h?aa?cc?k', # waacking
    'paa?nc?king?', # punking
    'locking4life',
    'dance crew[sz]?',
    'waving?', 'wavers?',
    'bott?ing?',
    'robott?ing?',
    'shuffle', 'melbourne shuffle',
    'jump\W?style[sz]?',
    'strutter[sz]?', 'strutting',
    'glides?', 'gliding', 
    'tuts?', 'tutting?', 'tutter[sz]?',
    'mtv\W?style', 'mtv\W?dance', 'videoclip', 'videodance', 'l\W?a\W?\Wstyle',
    'dance style[sz]',
    'n(?:ew|u)\W?styles?', 'all\W?style[zs]?', 'mix(?:ed)?\W?style[sz]?'
    'me against the music',
    'krump', 'krumping?', 'krumper[sz]?',
    'girl\W?s\W?hip\W?hop',
    'hip\W?hopp?er[sz]?',
    'street\W?jazz', 'street\W?funk', 'jazz\W?funk', 'boom\W?crack',
    'hype danc\w*',
    'social hip\W?hop', 'hip\W?hop social dance[sz]',
    '(?:new|nu|middle)\W?s(?:ch|k)ool hip\W?hop', 'hip\W?hop (?:old|new|nu|middle)\W?s(?:ch|k)ool',
    'newstyleurs?',
    'vogue', 'voguer[sz]?', 'vogue?ing', 'vogue fem',
    'mini.?ball', 'realness',
    'urban danc\w*',
    'pop\W{0,3}lock(?:ing?|er[sz]?)?'
]

easy_event_keywords = [
    'jams?', 'club', 'after\Wparty', 'pre\Wparty',
    'open sessions?', 'training',
]
club_and_event_keywords = [
    'sessions', 'practice',
    'shows?', 'performances?', 'contests?',
]

club_only_keywords = [
    'club',
    'bottle service',
    'table service',
    'coat check',
    #'rsvp',
    'free before',
    #'dance floor',
    #'bar',
    #'live',
    #'and up',
    'vip',
    'guest\W?list',
    'drink specials?',
    'resident dj\W?s?',
    'dj\W?s?',
    'techno', 'trance', 'indie', 'glitch',
    'bands?',
    'dress to',
    'mixtape',
    'decks',
    'r&b',
    'local dj\W?s?',
    'all night',
    'lounge',
    'live performances?',
    'doors', # doors open at x
    'restaurant',
    'hotel',
    'music shows?',
    'a night of',
    'dance floor',
    'beer',
    'blues',
    'bartenders?',
    'waiters?',
    'waitress(?:es)?',
    'go\Wgo',
    'gogo',
]

#TODO(lambert): use these
anti_dance_keywords  = [
    'jerk chicken',
    'poker tournaments?',
    'fashion competition',
    'wrestling competition',
    't?shirt competition',
    'shaking competition',
    'costume competition',
    'bottles? popping?',
    'poppin.? bottles?',
    'dance fitness',
    'lock down',
]
# battle royale
# go\W?go\W?danc(?:ers?|ing?)
#in\Whouse  ??
# 'brad houser'
# world class
# 1st class

# open mic
# Marvellous dance crew (uuugh)

#dj.*bboy
#dj.*bgirl

# 'vote for xx' in the subject
# 'vote on' 'vote for' in body, but small body of text
# release party

# methodology
# cardio
# fitness

# sometimes dance performances have Credits with a bunch of other performers, texts, production, etc. maybe remove these?

# HIP HOP INTERNATIONAL

# bad words in title of club events
# DJ
# Live
# Mon/Tue/Wed/Thu/Fri/Sat
# Guests?
# 21+ 18+

#TODO(lambert): use these to filter out shows we don't really care about
other_show_keywords = [
    'comedy',
    'poetry',
    'poets?',
    'spoken word',
    'painting',
    'juggling',
    'magic',
    'singing',
    'acting',
]

event_keywords = [
    'street\W?jam',
    'crew battle[sz]?', 'exhibition battle[sz]?',
    'apache line',
    'battle of the year', 'boty', 'compete', 'competitions?', 'battles?', 'tournaments?', 'preselection',
    'jurys?', 'jurados', 'judge[sz]?',
    'showcase',
    r'(?:seven|7)\W*(?:to|two|2)\W*smoke',
    'c(?:y|i)ph(?:a|ers?)',
    'session', # the plural 'sessions' is handled up above under club-and-event keywords
    'workshops?', 'class with', 'master\W?class(?:es)?', 'auditions?', 'try\W?outs?', 'class(?:es)?', 'lessons?', 'courses?',
    'classi',
    'cours', 'clases?', 'corso', 
    'abdc', 'america\W?s best dance crew',
    'crew\W?v[sz]?\W?crew',
    'prelims?',
    'bonnie\s*(?:and|&)\s*clyde',
] + [r'%s[ -]?(?:v/s|vs?\.?|x|×|on)[ -]?%s' % (i, i) for i in range(12)]


dance_wrong_style_keywords = [
    'styling', 'salsa', 'bachata', 'balboa', 'tango', 'latin', 'lindy', 'lindyhop', 'swing', 'wcs', 'samba',
    'barre',
    'musical theat(?:re|er)',
    'pole dance', 'flirt dance',
    'bollywood', 'kalbeliya', 'bhawai', 'teratali', 'ghumar',
    'oriental', 'oriente', 'orientale',
    'tahitian dancing',
    'folkloric',
    'kizomba',
    'burlesque',
    'technique', 'limon',
    'clogging',
    'zouk',
    # Sometimes used in studio name even though it's still a hiphop class:
    #'ballroom',
    #'ballet',
    'jazz', 'tap', 'contemporary',
    'african',
    'zumba', 'belly\W?danc(?:e(?:rs?)?|ing)', 'bellycraft', 'worldbellydancealliance',
    'soca',
    'flamenco',
]

manual_dance_keywords_regex = None
good_capturing_keyword_regex = None

def build_regexes():
    global manual_dance_keywords_regex
    global good_capturing_keyword_regex
    if good_capturing_keyword_regex:
        return

    manual_dance_keywords = []
    import os
    if os.getcwd().endswith('mapreduce'): #TODO(lambert): what is going on with appengine sticking me in the wrong starting directory??
        base_dir = '..'
    else:
        base_dir = '.'
    for filename in ['bboy_crews', 'bboys', 'choreo_crews', 'choreo_dancers', 'choreo_keywords', 'competitions', 'freestyle_crews', 'freestyle_dancers']:
        f = open('%s/dance_keywords/%s.txt' % (base_dir, filename))
        for line in f.readlines():
            line = re.sub('\s*#.*', '', line.strip())
            if not line:
                continue
            if line.endswith(',0'):
                line = line[:-2]
            else:
                manual_dance_keywords.append(line)

    if manual_dance_keywords:
        manual_dance_keywords_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(manual_dance_keywords))
    else:
        manual_dance_keywords_regex = re.compile(r'NEVER_MATCH_BLAGSDFSDFSEF')

    good_capturing_keyword_regex = re.compile(r'(?i)\b(%s)\b' % '|'.join(easy_dance_keywords + easy_event_keywords + dance_keywords + event_keywords + club_and_event_keywords + dance_and_music_keywords + easy_choreography_keywords + manual_dance_keywords))

dance_wrong_style_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(dance_wrong_style_keywords))
dance_and_music_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(dance_and_music_keywords))
club_and_event_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(club_and_event_keywords))
easy_choreography_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(easy_choreography_keywords))
club_only_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(club_only_keywords))

easy_dance_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(easy_dance_keywords))
easy_event_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(easy_event_keywords))
dance_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(dance_keywords))
event_regex = re.compile(r'(?i)\b(?:%s)\b' % '|'.join(event_keywords))

bad_capturing_keyword_regex = re.compile(r'(?i)\b(%s)\b' % '|'.join(club_only_keywords + dance_wrong_style_keywords))


# NOTE: Eventually we can extend this with more intelligent heuristics, trained models, etc, based on multiple keyword weights, names of teachers and crews and whatnot

def get_relevant_text(fb_event):
    search_text = (fb_event['info'].get('name', '') + ' ' + fb_event['info'].get('description', '')).lower()
    return search_text

class ClassifiedEvent(object):
    def __init__(self, fb_event):
        if 'name' not in fb_event['info']:
            logging.info("fb event id is %s has no name, with value %s", fb_event['info']['id'], fb_event)
            self.search_text = ''
        else:
            self.search_text = get_relevant_text(fb_event)

    @timed
    def classify(self):
        build_regexes()
        manual_dance_keywords_matches = set(manual_dance_keywords_regex.findall(self.search_text))
        easy_dance_matches = set(easy_dance_regex.findall(self.search_text))
        easy_event_matches = set(easy_event_regex.findall(self.search_text))
        dance_matches = set(dance_regex.findall(self.search_text))
        event_matches = set(event_regex.findall(self.search_text))
        dance_wrong_style_matches = set(dance_wrong_style_regex.findall(self.search_text))
        dance_and_music_matches = set(dance_and_music_regex.findall(self.search_text))
        club_and_event_matches = set(club_and_event_regex.findall(self.search_text))
        easy_choreography_matches = set(easy_choreography_regex.findall(self.search_text))
        club_only_matches = set(club_only_regex.findall(self.search_text))

        self.found_dance_matches = dance_matches.union(easy_dance_matches).union(dance_and_music_matches).union(manual_dance_keywords_matches).union(easy_choreography_matches)
        self.found_event_matches = event_matches.union(easy_event_matches).union(club_and_event_matches)
        self.found_wrong_matches = dance_wrong_style_matches.union(club_only_matches)

        if len(manual_dance_keywords_matches) >= 1:
            self.dance_event = 'obvious dancer or dance crew or battle'
        # one critical dance keyword
        elif len(dance_matches) >= 1:
            self.dance_event = 'obvious dance style'
        elif len(dance_and_music_matches) >= 1 and (len(event_matches) + len(easy_choreography_matches)) >= 1:
            self.dance_event = 'hiphop/funk and good event type'
        # one critical event and a basic dance keyword and not a wrong-dance-style and not a generic-club
        elif len(easy_dance_matches) >= 1 and (len(event_matches) + len(easy_choreography_matches)) >= 1 and len(dance_wrong_style_matches) == 0:
            self.dance_event = 'dance event thats not a bad-style'
        elif len(easy_dance_matches) >= 1 and len(club_and_event_matches) >= 1 and len(dance_wrong_style_matches) == 0 and len(club_only_matches) == 0:
            self.dance_event = 'dance show thats not a club'
        else:
            self.dance_event = False

    def is_dance_event(self):
        return bool(self.dance_event)
    def reason(self):
        return self.dance_event
    def dance_matches(self):
        return self.found_dance_matches
    def event_matches(self):
        return self.found_event_matches
    def wrong_matches(self):
        return self.found_wrong_matches
    def match_score(self):
        if self.is_dance_event():
            combined_matches = self.found_dance_matches.union(self.found_event_matches)
            return len(combined_matches)
        else:
            return 0
    def keyword_density(self):
        combined_matches = self.found_dance_matches.union(self.found_event_matches)
        fraction_matched = 1.0 * len(combined_matches) / len(re.split(r'\W+', self.search_text))
        if not fraction_matched:
            return -100
        else:
            return int(math.log(fraction_matched))


def get_classified_event(fb_event):
    classified_event = ClassifiedEvent(fb_event)
    classified_event.classify()
    return classified_event

def relevant_keywords(fb_event):
    build_regexes()
    text = get_relevant_text(fb_event)
    good_keywords = good_capturing_keyword_regex.findall(text)
    bad_keywords = bad_capturing_keyword_regex.findall(text)
    return sorted(set(good_keywords).union(bad_keywords))

@skip_filter
def highlight_keywords(text):
    build_regexes()
    text = good_capturing_keyword_regex.sub('<span class="matched-text">\\1</span>', text)
    text = bad_capturing_keyword_regex.sub('<span class="bad-matched-text">\\1</span>', text)
    return text
