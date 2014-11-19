# -*-*- encoding: utf-8 -*-*-
#

import itertools
import re
import regex_keywords
from util import re_flatten

# The magical repository of all dance keywords
_keywords = {}
_regex_strings = {}
_regexes = {}

class GrammarRule(object):
    """The entire grammar rule tree must be composed of these."""

class Keyword(GrammarRule):
    def __init__(self, keyword):
        self.keyword = keyword

    def children(self):
        return []

    def as_expanded_regex(self):
        return get_regex_string(self)

    def as_token_regex(self):
        return self.keyword

    def replace_string(self):
        return self.keyword

    def __repr__(self):
        return 'Keyword(%r)' % self.keyword


def _key(tokens):
    return tuple(sorted(tokens))

def get_regex_string(*tokens):
    token_key = _key(tokens)
    if token_key not in _regex_strings:
        _regex_strings[token_key] = re_flatten.construct_regex(get(*tokens))
    return _regex_strings[token_key]

#TODO(lambert): move this function out of here in some way, as it is an artifact of the old-way
def get_regex(*tokens):
    token_key = _key(tokens)
    if token_key not in _regexes:
        # TODO(lambert): this is regexes, while function name is regex. We need to fix this (since make_regex is a different function)
        _regexes[token_key] = regex_keywords.make_regexes(get(*tokens))
    return _regexes[token_key]

def _flatten(listOfLists):
    "Flatten one level of nesting"
    return list(itertools.chain.from_iterable(listOfLists))

def get(*tokens):
    return _flatten(_keywords[token] for token in tokens)

def token(token_input):
    assert not re.match('\W', token_input)
    return Keyword('_%s_' % token_input)

def add(token, keywords):
    # If anything has been built off of these, when we want to add new stuff, then we need to raise an error
    assert token not in _regexes
    assert token not in _regex_strings
    if token in _keywords:
        _keywords[token] += keywords
    else:
        _keywords[token] = keywords

# 'crew' biases dance one way, 'company' biases it another
EASY_DANCE = token('EASY_DANCE')
add(EASY_DANCE, [
    'dance style[sz]',
    'dances?', "dancin[g']?", 'dancers?',
    u'댄스', # korean dance
    u'댄서', # korean dancer
    u'танцы', # russian dancing
    u'танцоров', # russian dancers
    u'танцуват', # bulgarian dance
    u'танцува', # bulgarian dance
    u'танцовия', # bulgarian dance
    u'изтанцуват', # bulgarian dancing
    u'ダンサー', # japanese dance
    u'ダンス', # japanese dance
    u'춤.?', # korean dance
    u'추고.?.?', # korean dancing
    u'댄서.?.?', # korean dancers
    u'踊り', # japanese dance
    u'רוקד', # hebrew dance
    u'רקדם', # hebrew dancers
    u'רוקדים', # hebrew dance
    u'רקדנים', # hebrew dancers
    u'舞者', # chinese dancer
    u'舞技', # chinese dancing
    u'舞', # chinese dance
    u'舞蹈', # chinese dance
    u'排舞', # chinese dance
    u'แดนซ์', # dance thai
    u'เต้น', # dance thai
    u'กเต้น', # dancers thai
    'danse\w*', # french and danish
    'taniec', # dance polish
    u'tane?[cč][íú\w]*', # dance slovak/czech
    u'zatanč\w*', # dance czech
    u'tańe?c\w*', # dance polish/czech
    u'danç\w*', # dance portuguese
    'danza\w*', # dance italian
    u'šok\w*', # dance lithuanian
    'tanz\w*', # dance german
    'tanssi\w*', # finnish dance
    'bail[ae]\w*', # dance spanish
    'danzas', # dance spanish
    'ballerin[io]', # dancer italian
    'dansare', # dancers swedish
    'dansat', # dancing swedish
    'dansama', # dancers swedish
    'dansa\w*', # dance-* swedish
    'dansgolv', # dance floor swedish
    'dans', # swedish danish dance
    u'tänzern', # dancer german
    u'танчер', # dancer macedonian
    u'танцовиот', # dance macedonian
    'footwork',
    'plesa', # dance croatian
    'plesu', # dancing croatian
    u'nhảy', # dance vietnamese
    u'tänzer', # dancer german
])

EASY_CHOREO = token('EASY_CHOREO')
add(EASY_CHOREO, [
    u'(?:ch|k|c)oe?re[o|ó]?gra(?:ph|f)\w*', #english, italian, finnish, swedish, german, lithuanian, polish, italian, spanish, portuguese, danish
    'choreo',
    u'chorée', # french choreo
    u'chorégraph\w*', # french choreographer
    u'кореограф', # macedonian
])

GOOD_INSTANCE_OF_BAD_CLUB = token('GOOD_INSTANCE_OF_BAD_CLUB')
add(GOOD_INSTANCE_OF_BAD_CLUB, [
    'evelyn\W+champagne\W+king',
    'water\W?bottles?',
    'genie in (?:the|a) bottle',
])

BAD_CLUB = token('BAD_CLUB')
add(BAD_CLUB, [
    'bottle\W?service',
    'popping?\W?bottles?',
    'bottle\W?popping?',
    'bottles?',
    'grey goose',
    'champagne',
    'belvedere',
    'ciroc',
])

CYPHER = token('CYPHER')
add(CYPHER, [
    'c(?:y|i)ph(?:a|ers?)',
    u'サイファ', # japanese cypher
    u'サイファー', # japanese cypher
    u'サークル', # japanese circle
    u'サーク', # japanese circle
    'cerchi', # italian circle/cypher
    u'ไซเฟอร์', # thai cypher
    u'싸이퍼.?', # korean cypher
])

# if somehow has funks, hiphop, and breaks, and house. or 3/4? call it a dance event?

AMBIGUOUS_DANCE_MUSIC = token('AMBIGUOUS_DANCE_MUSIC')
add(AMBIGUOUS_DANCE_MUSIC, [
    'hip\W?hop',
    u'嘻哈', # chinese hiphop
    u'ההיפ הופ', # hebrew hiphop
    u'хипхоп', # macedonian hiphop
    u'ヒップホップ', # hiphop japanese
    u'힙합', # korean hiphop
    'hip\W?hop\w*', # lithuanian, polish hiphop
    'all\W?style[zs]?',
    'tou[ts]\W?style[zs]?', # french all-styles
    'tutti gli stili', # italian all-styles
    'be\W?bop',
    'shuffle',
    'funk',
    'dance\W?hall\w*',
    'ragga',
    'hype',
    'new\W?jack\W?swing',
    'gliding', 
    # 'breaks', # too many false positives
    'boogaloo',
    "breakin[g']?", 'breakers?',
    'jerk',
    'kpop',
    'rnb',
    "poppin\'?",
    'hard\Whitting',
    'electro\W?dance',
    'old\W?school hip\W?hop',
    '90\W?s hip\W?hop',
    'vogue',
    u'フリースタイル', # japanese freestyle
    'b\W?boy\w*', # 'bboyev' in slovak
])

# hiphop dance. hiphop dans?
DANCE = token('DANCE')
add(DANCE, [
    'street\W?jam',
    'breakingu', #breaking polish
    u'breaktánc', # breakdance hungarian
    u'ブレイク', # breakdance japanese
    'jazz rock',
    'funk\W?style[sz]?',
    'poppers?', 'popp?i?ng', # listing poppin in the ambiguous keywords
    'poppeurs?',
    'commercial hip\W?hop',
    'hip\W?hop dance',
    "jerk(?:ers?|in[g']?)",
    u'스트릿', # street korean
    u'ストリートダンス', # japanese streetdance
    u'街舞', # chinese streetdance / hiphop
    u'gatvės šokių', # lithuanian streetdance
    'katutanssi\w*', # finnish streetdance
    "bre?ak\W?dancin[g']?", 'bre?ak\W?dancer?s?',
    'break\W?danc\w+',
    'rock\W?dan[cs]\w+',
    '(?:lite|light)\W?feet',
    "gettin[g']?\W?(?:lite|light)",
    "turfin[g']?", 'turf danc\w+', "flexin[g']?", "buckin[g']?", "jookin[g']?",
    'b\W?boy[sz]?', "b\W?boyin[g']?", 'b\W?girl[sz]?', "b\W?girlin[g']?", 'power\W?moves?', "footworkin[g']?",
    u'파워무브', # powermove korean
    'breakeuse', # french bgirl
    'footworks', # spanish footworks
    "top\W?rock(?:s|er[sz]?|in[g']?)?", "up\W?rock(?:s|er[sz]?|in[g']?|)?",
    'houser[sz]?',
    'dance house', # seen in italian
    'soul dance',
    u'ソウルダンス', # soul dance japanese
    "lock(?:er[sz]?|in[g']?)?", 'lock dance',
    u'ロッカーズ', # japanese lockers
    u'ロッカ', # japanese lock
    "[uw]h?aa?c?c?k(?:er[sz]?|inn?[g']?)", # waacking
    "paa?nc?kin[g']?", # punking
    'locking4life',
    'dance crew[sz]?',
    "wavin[g']?", 'wavers?',
    'liquid\W+dance'
    'liquid\W+(?:\w+\W+)?digitz',
    'finger\W+digitz',
    'toy\W?man',
    'puppet\W?style',
    "bott?in[g']?",
    "robott?in[g']?",
    'melbourne shuffle',
    'strutter[sz]?', 'strutting',
    "tuttin[g']?", 'tutter[sz]?',
    'mj\W+style', 'michael jackson style',
    'mtv\W?style', 'mtv\W?dance', 'videoclip\w+', 'videodance',
    'hip\W?hop\Wheels',
    # only do la-style if not salsa? http://www.dancedeets.com/events/admin_edit?event_id=292605290807447
    # 'l\W?a\W?\Wstyle',
    'l\W?a\W?\Wdance',
    'n(?:ew|u)\W?style',
    'n(?:ew|u)\W?style\Whip\W?hop',
    'hip\W?hop\Wn(?:ew|u)\W?style',
    'mix(?:ed)?\W?style[sz]?', 'open\W?style[sz]',
    'all\W+open\W?style[sz]?',
    'open\W+all\W?style[sz]?',
    'me against the music',
    'krump', "krumpin[g']?", 'krumper[sz]?',
    'ragga\W?jamm?',
    'girl\W?s\W?hip\W?hop',
    'hip\W?hopp?er[sz]?',
    'street\W?jazz', 'street\W?funk',
    'jazz\W?funk', 'funk\W?jazz',
    'boom\W?crack',
    'hype danc\w*',
    'social hip\W?hop', 'hip\W?hop social dance[sz]', 'hip\W?hop party dance[sz]',
    'hip\W?hop grooves',
    '(?:new|nu|middle)\W?s(?:ch|k)ool\W\W?hip\W?hop', 'hip\W?hop\W\W?(?:old|new|nu|middle)\W?s(?:ch|k)ool',
    'newstyleurs?',
    'voguer[sz]?', "vogue?in[g']?", 'vogue fem', 'voguin',
    'vouge', "vougin[g']?",
    'fem queen', 'butch queen',
    'mini\W?ball', 'realness',
    'new\W?style hustle',
    'urban danc\w*',
    'urban style[sz]',
    'urban contemporary',
    u'dan[çc]\w* urban\w*',
    'dan\w+ urbai?n\w+', # spanish/french urban dance
    'baile urbai?n\w+', # spanish urban dance
    'estilo\w* urbai?n\w+', # spanish urban styles
    "pop\W{0,3}(?:(?:N|and|an)\W{1,3})?lock(?:in[g']?|er[sz]?)?",
])
# Crazy polish sometimes does lockingu and lockingy. Maybe we need to do this more generally though.
add(DANCE, [x+'u' for x in get(DANCE)])
# TODO(lambert): Is this a safe one to add?
# http://en.wikipedia.org/wiki/Slovak_declension
# dance_keywords = dance_keywords + [x+'y' for x in dance_keywords] 

# hiphop dance. hiphop dans?

# house battles http://www.dancedeets.com/events/admin_edit?event_id=240788332653377
HOUSE = token('HOUSE')
add(HOUSE, [
    'house',
    u'하우스', # korean house
    u'ハウス', # japanese house
    u'хаус', # russian house
])

FREESTYLE = token('FREESTYLE')
add(FREESTYLE, [
    'free\W?style(?:r?|rs?)',
])

STREET = token('STREET')
add(STREET, [
    'street',
])

EASY_BATTLE = token('EASY_BATTLE')
add(EASY_BATTLE, [
    'jams?', 
])

EASY_EVENT = token('EASY_EVENT')
add(EASY_EVENT, [
    'club', 'after\Wparty', 'pre\Wparty',
    u'クラブ',  # japanese club
    'open sessions?',
    'training',
])

CONTEST = token('CONTEST')
add(CONTEST, [
    'contests?',
    'concours', # french contest
    'konkurrencer', # danish contest
    'dancecontests', # dance contests german
])
PRACTICE = token('PRACTICE')
add(PRACTICE, [
    'sesja', # polish session
    'sessions', 'practice',
])

PERFORMANCE = token('PERFORMANCE')
add(PERFORMANCE, [
    'shows?', 'performances?',
    'show\W?case',
    u'représentation', # french performance
    u'ショーケース', # japanese showcase
    u'秀', # chinese show
    u'的表演', # chinese performance
    u'表演', # chinese performance
    u'vystoupení', # czech performances
    u'výkonnostních', # czech performance
    u'изпълнението', # bulgarian performance
    u'パフォーマンス', # japanese performance
    # maybe include 'spectacle' as well?
    'esibizioni', #italian performance/exhibition
])


CLUB_ONLY = token('CLUB_ONLY')
add(CLUB_ONLY, [
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
    'residency',
    'ravers?',
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
    'bartenders?',
    'waiters?',
    'waitress(?:es)?',
    'go\W?go',
])

PREPROCESS_REMOVAL = token('PREPROCESS_REMOVAL')
add(PREPROCESS_REMOVAL, [
    # positive
    'tap water', # for theo and dominque's jam

    # negative
    "america's got talent",
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
    'lock up',
    'latin street dance',
    'whack music',
    'wack music',
    'marvellous dance crew',
    '1st class',
    'first class',
    'world class',
    'pledge class',
    'world\Wclass',
    'top class',
    'class\W?rnb',
    'class act',
    'go\W?go\W?danc(?:ers?|ing?)',
    'latin street',
    'ice\w?breaker',

    'straight up', # up rock
    'tear\W?jerker', # jerker
    'in-strutter', # strutter
    'on stage',
    'main\Wstage',
    'of course',
    'breaking down',
    'ground\W?breaking',
    '(?:second|2nd) stage',
    'open house',
    'hip\W?hop\W?kempu?', # refers to hiphop music!
    'camp\W?house',
    'in\W?house',
    'lock in',
    'juste debout school',
    'baile funk',
])

# battle freestyle ?
# dj battle
# battle royale
# http://www.dancedeets.com/events/admin_edit?event_id=208662995897296
# mc performances
# beatbox performances
# beat 
# 'open cyphers'
# freestyle
#in\Whouse  ??
# 'brad houser'

# open mic

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

# boogiezone if not contemporary?
# free style if not salsa?


#TODO(lambert): use these to filter out shows we don't really care about
#TODO: UNUSED
OTHER_SHOW = token('OTHER_SHOW')
add(OTHER_SHOW, [
    'comedy',
    'poetry',
    'poets?',
    'spoken word',
    'painting',
    'juggling',
    'magic',
    'singing',
    'acting',
])



BATTLE = token('BATTLE')
add(BATTLE, [
    'battle of the year', 'boty', 'compete',
    'competitions?',
    'konkurrence', # danish competition
    'competencia', # spanish competition
    u'competición', # spanish competition
    u'compétition', # french competition
    u'thi nhảy', # dance competition vietnam
    'kilpailu\w*' # finish competition
    'konkursams', # lithuanian competition
    'verseny', # hungarian competition
    'championships?',
    'champs?',
    u'čempionatams', # lithuanian championship
    'campeonato', # spanish championship
    'meisterschaft', # german championship
    'concorsi', # italian competition
    u'danstävling', # swedish dance competition
    u'แข่งขัน', # thai competition
    'crew battle[sz]?', 'exhibition battle[sz]?',
    'battles?',
    'battlu(?:je)?', # french czech
    u'比賽', # chinese battle
    u'バトル', # japanese battle
    u'битката', # bulgarian battle
    'batallas', # battles spanish
    'zawody', # polish battle/contest
    'walki', # polish battle/fight
    u'walkę', # polish battle/fight
    'bitwa', # polish battle
    u'bitwę', # polish battle
    'bitwach', # polish battle
    u'バトル', # japanese battle
    'tournaments?',
    'tournoi', # french tournament
    u'大会', # japanese tournament
    u'トーナメント', # japanese tournament
    'turnie\w*', # tournament polish/german
    u'giải đấu', # tournament vietnamese
    u'thi đấu', # competition vietnamese
    u'състезанието', # competition bulgarian
    u'đấu', # game vietnamese
    'turneringer', # danish tournament
    'preselections?',
    u'présélections?', # preselections french
    'crew\W?v[sz]?\W?crew',
    'prelims?',
    u'初賽', # chinese preliminaries
])

CLASS = token('CLASS')
add(CLASS, [
    'work\W?shop\W?s?',
    'ws', # japanese workshop WS
    'w\.s\.', # japanese workshop W.S.
    u'ワークショップ', # japanese workshop
    'cursillo', # spanish workshop
    'ateliers', # french workshop
    'workshopy', # czech workshop
    u'סדנאות', # hebrew workshops
    u'סדנה', # hebew workshop
    # 'taller', # workshop spanish
    'delavnice', # workshop slovak
    'talleres', # workshops spanish
    'radionicama', # workshop croatian
    'warsztaty', # polish workshop
    u'warsztatów', # polish workshop
    u'seminarų', # lithuanian workshop
    'taller de', # spanish workshop
    'intensives?',
    'intensivo', # spanish intensive
    'class with', 'master\W?class(?:es)?',
    'company class',
    u'мастер-класса?', # russian master class
    u'классa?', # russian class
    'class(?:es)?', 'lessons?', 'courses?',
    'klass(?:en)?', # slovakian class
    u'수업', # korean class
    u'수업을', # korean classes
    'lekc[ie]', # czech lesson
    u'課程', # course chinese
    u'課', # class chinese
    u'堂課', # lesson chinese
    u'コース', # course japanese
    'concorso', # course italian
    'kurs(?:y|en)?', # course german/polish
    'aulas?', # portuguese class(?:es)?
    u'특강', # korean lecture
    'lektion(?:en)?', # german lecture
    'lekcie', # slovak lessons
    'dansklasser', # swedish dance classes
    'lekcj[ai]', # polish lesson
    'eigoje', # lithuanian course
    'pamokas', # lithuanian lesson
    'kursai', # course lithuanian
    'lez.', #  lesson italian
    'lezione', # lesson italian
    'lezioni', # lessons italian
    u'zajęciach', # class polish
    u'zajęcia', # classes polish
    u'คลาส', # class thai
    'classe', # class italian
    'classi', # classes italin
    'klasser?', # norwegian class
    'cours', 'clases?',
    'camp',
    'kamp',
    'kemp',
    'formazione', # training italian
    'formazioni', # training italian
    u'トレーニング', # japanese training
])

AUDITION = token('AUDITION')
add(AUDITION, [
    'try\W?outs?',
    'casting',
     'casting call',
    'castingul', # romanian casting
    'auditions?',
    'audicija', # audition croatia
    'audiciones', # spanish audition
    'konkurz', # audition czech
    u'試鏡', # chinese audition
    'audizione', # italian audition
    'naborem', # polish recruitment/audition
])

EVENT = token('EVENT')
add(EVENT, [
    'open circles',
    'session', # the plural 'sessions' is handled up above under club-and-event keywords
    u'セッション', # japanese session
    u'練習会', # japanese training
    u'練習', # japanese practice
    'abdc', 'america\W?s best dance crew',
])

def _generate_n_x_n_keywords():
    english_digit_x_keywords = [
        'v/s',
        r'vs?\.?',
        'on',
        'x',
        u'×',
    ]
    digit_x_keywords = english_digit_x_keywords + [
        'na',
        'mot',
        'contra',
        'contre',
    ]
    digit_x_string = '|'.join(digit_x_keywords)
    english_digit_x_string = '|'.join(english_digit_x_keywords)
    n_x_n_keywords = [u'%s[ -]?(?:%s)[ -]?%s' % (i, digit_x_string, i) for i in range(12)[1:]]
    n_x_n_keywords += [u'%s[ -](?:%s)[ -]%s' % (i, english_digit_x_string, i) for i in ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']]
    return n_x_n_keywords

N_X_N = token('N_X_N')
add(N_X_N, _generate_n_x_n_keywords())

JUDGE = token('JUDGE')
add(JUDGE, [
    'jurys?',
    'jurados?', # spanish jury
    u'журито', # bulgarian jury
    'judge[sz]?',
    'jures', # french jury
    '(?:les? )?juges?', # french judges
    'giudici', # italian judges
    u'השופט', # hebrew judge
    u'השופטים', # hebrew judges
    u'teisėjai', # lithuanian judges
    'tuomaristo', # jury finnish
    'jueces', # spanish judges
    'juriu', # romanian judges
    'giuria', # jury italian
    u'評審', # chinese judges
    u'評判', # chinese judges
    u'評判團', # chinese judges
    u'審査員', # japanese judges
    u'ジャッジ', # japanese judges
])



FRENCH_EVENT = token('FRENCH_EVENT')
add(FRENCH_EVENT, [
    'spectacle',
    'stage',
])

ITALIAN_EVENT = token('ITALIAN_EVENT')
add(ITALIAN_EVENT, [
    'stage',
])

AMBIGUOUS_CLASS = token('AMBIGUOUS_CLASS')
add(AMBIGUOUS_CLASS, [
    'stage',
    'stages',
])

DANCE_WRONG_STYLE = token('DANCE_WRONG_STYLE')
add(DANCE_WRONG_STYLE, [
    'styling', 'salsa', 'bachata', 'balboa', 'tango', 'latin', 'lindy', 'lindyhop', 'swing', 'wcs', 'samba',
    'latines', 'quickstep', 'rumba', 'cha\W?cha',
    'blues',
    'waltz',
    'salsy', # salsa czech
    'salser[oa]s?',
    'kizomba',
    'disco dance',
    'disco tan\w+', # czech disco dance
    'milonga',
    'dance partner',
    'cha cha',
    'hula',
    'tumbling',
    'exotic',
    'cheer',
    'barre',
    'butoh',
    'contato improv\w*',
    'contact improv\w*',
    'contratto mimo', # italian contact mime
    'musical theat(?:re|er)',
    'pole danc\w+', 'flirt danc\w+',
    'go\W?go',
    'bollywood', 'kalbeliya', 'bhawai', 'teratali', 'ghumar',
    'indienne',
    'persiana?',
    'arabe', 'arabic', 'araba',
    'oriental\w*', 'oriente', 
    'cubana',
    'capoeira',
    'tahitian dancing',
    'tahitienne',
    'folklor\w+',
    'kizomba',
    'burlesque',
    u'バーレスク', # burlesque japan
    'limon',
    'artist\Win\Wresidence',
    'residency',
    'disciplinary',
    'reflective',
    'clogging',
    'zouk',
    'african dance',
    'afro dance',
    'afro mundo',
    'class?ic[ao]',
    'acroyoga',
    'kirtan',
    'hoop\W?dance',
    'modern dance',
    'pilates',
    'tribal',
    'jazz', 'tap', 'contemporary',
    u'súčasný', # contemporary slovak
    u'współczesnego', # contemporary polish
    'contempor\w*', # contemporary italian, french
    'africa\w+',
    'sabar',
    'aerial silk',
    'silk',
    'aerial',
    'zumba', 'belly\W?danc(?:e(?:rs?)?|ing)', 'bellycraft', 'worldbellydancealliance',
    'soca',
    'flamenco',
    'technique',
    'guest artists?',
    'partnering',
    'charleston',
])

# These are okay to see in event descriptions, but we don't want it to be in the event title, or it is too strong for us
DANCE_WRONG_STYLE_TITLE = token('DANCE_WRONG_STYLE_TITLE')
add(DANCE_WRONG_STYLE_TITLE, get(DANCE_WRONG_STYLE))
add(DANCE_WRONG_STYLE_TITLE, [
    # Sometimes used in studio name even though it's still a hiphop class:
    'ballroom',
    'ballet',
    'yoga',
    'talent shows?', # we don't care about talent shows that offer dance options
    'stiletto',
    '\w+ball', # basketball/baseball/football tryouts
])


#TODO(lambert): we need to remove the empty CONNECTOR here, and probably spaces as well, and handle that in the rules? or just ensure this never gets applied except as part of rules
CONNECTOR = token('CONNECTORS')
add(CONNECTOR, [
    ' ?',
    ' di ',
    ' de ',
    ' ?: ?',
    u'な', # japanese
    u'の', # japanese
    u'的', # chinese
#TODO(lambert): explore adding these variations, and their impact on quality
#    r' ?[^\w\s] ?',
#    ' \W ',
])

AMBIGUOUS_WRONG_STYLE = token('AMBIGUOUS_WRONG_STYLE')
add(AMBIGUOUS_WRONG_STYLE, [
    'modern',
    'ballet',
    'ballroom',
])


WRONG_NUMBERED_LIST = token('WRONG_NUMBERED_LIST')
add(WRONG_NUMBERED_LIST, [
    'track(?:list(?:ing)?)?',
    'release',
    'download',
    'ep',
])

WRONG_AUDITION = token('WRONG_AUDITIONS')
add(WRONG_AUDITION, [
    'sing(?:ers?)?',
    'singing',
    'model',
    'poet(?:ry|s)?',
    'act(?:ors?|ress(?:es)?)?',
    'mike portoghese', # TODO(lambert): When we get bio removal for keyword matches, we can remove this one
])

WRONG_BATTLE = token('WRONG_BATTLES')
add(WRONG_BATTLE, [
    'talent',
    'beatbox',
    'rap',
    'swimsuit',
    'tekken',
    'capcom',
    'games?',
    'game breaking',
    'videogames?',
    'sexy',
    'lingerie',
    'judge jules',
    'open mic',
    'producer',
])

WRONG_BATTLE_STYLE = token('WRONG_BATTLE_STYLES')
add(WRONG_BATTLE_STYLE, [
    '(?:mc|emcee)\Whip\W?hop',
    'emcee',
    'rap',
    'beat',
    'beatbox',
    'dj\W?s?',
    'producer',
    'performance',
    'graf(?:fiti)?',
])

#TODO: use
# solo performance
# solo battle
# crew battle
# team battle
# these mean....more
#TODO: UNUSED
FORMAT_TYPE = token('FORMAT_TYPE')
add(FORMAT_TYPE, [
    'solo',
    u'ソロ', # japanese solo
    'team',
    u'チーム', # japanese team
    'crew',
    u'クルー', # japanese crew
])

BAD_COMPETITION = token('BAD_COMPETITION')
add(BAD_COMPETITION, [
    'video',
    'fundrais\w+',
    'likes?',
    'votes?',
    'votas?', # spanish votes
    u'głosowani\w+', # polish vote
    'support',
    'follow',
    '(?:pre)?sale',
])


VOGUE = token('VOGUE')
add(VOGUE, [
    'butch realness',
    'butch queen',
    'vogue fem',
    'hand performance',
    'face performance',
    'femme queen',
    'sex siren',
    'vogue?ing',
    'voguin',
    'voguer[sz]?',
    'trans\W?man',
])
EASY_VOGUE = token('EASY_VOGUE')
add(EASY_VOGUE, [
    'never walked',
    'virgin',
    'drags?',
    'twist',
    'realness',
    'runway',
    'female figure',
    'couture',
    'butch',
    'ota',
    'open to all',
    'f\\.?q\\.?',
    'b\\.?q\\.?',
    'vogue',
    'house of',
    'category',
    'troph(?:y|ies)',
    'old way',
    'new way',
    'ball',
])

SEMI_BAD_DANCE = token('SEMI_BAD_DANCE')
add(SEMI_BAD_DANCE, [
    'technique',
    'dance company',
    'explore',
    'visual',
    'stage',
    'dance collective',
])

#TODO(lambert): should these be done here, as additional keywords?
# Or should they be done as part of the grammar, that tries to combine these into rules of some sort?

OBVIOUS_BATTLE = token('OBVIOUS_BATTLE')
add(OBVIOUS_BATTLE, [
    'apache line',
    r'(?:seven|7)\W*(?:to|two|2)\W*(?:smoke|smook|somke)',
])

# TODO(lambert): is it worth having all these here as super-basic keywords? Should we instead just list these directly in rules.py?
BONNIE_AND_CLYDE = token('BONNIE_AND_CLYDE')
add(BONNIE_AND_CLYDE, [
    'bonnie\s*(?:and|&)\s*clyde'
])

KING_OF_THE = token('KING_OF_THE')
add(KING_OF_THE, [
    'king of (?:the )?',
])

KING = token('KING')
add(KING, [
    'king'
])
