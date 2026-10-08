#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
J! TRAINER - a one-player Jeopardy! trainer for the Linux terminal.

Plain text only: no graphics and no third-party packages (Python 3.7+).

FIRST RUN
    python3 jeopardy_trainer.py --fetch      # download real clues (about 14 MB)
    python3 jeopardy_trainer.py              # choose a seed from a menu and play

SEEDS (question sets)
    python3 jeopardy_trainer.py --seed "africa geography questions"
    python3 jeopardy_trainer.py --seed "bodies of water"
    python3 jeopardy_trainer.py --seed "presidents of the USA"
    python3 jeopardy_trainer.py --seed shakespeare
    python3 jeopardy_trainer.py --seed "pop culture"
    python3 jeopardy_trainer.py --seed music
    python3 jeopardy_trainer.py --seed mixed     # all six themes on one board
    python3 jeopardy_trainer.py --seed any       # anything, like a real game
    Any other text filters by category name:  --seed opera   --seed "world war"

OTHER OPTIONS
    --quick        one round + Final (about 10 minutes) instead of a full game
    --timer 15     seconds allowed per response (press Enter in time)
    --strict       responses must be phrased as a question, as on the show
    --since 2025   only use clues that aired in 2025 or later
    --fetch 12     download the 12 newest seasons instead of the default 6
    --scores       show the high-score tables
    --list         show every seed and how many categories it has
    --practice     play the built-in practice set instead of show clues
    --help         everything else

HOW A GAME WORKS
    Jeopardy! round (6 categories, $200-$1000, 1 Daily Double), Double Jeopardy!
    round ($400-$2000, 2 Daily Doubles), then Final Jeopardy! with a wager.
    Right = +value, wrong = -value, Enter alone = pass (no penalty, like not
    buzzing in). Daily Doubles and Final must be answered. High scores are kept
    per seed. A Coryat score (no wagering, no Final) is shown too - it is the
    number serious players track.

WHERE THE CLUES COME FROM
    --fetch downloads season files from a public, fan-maintained archive of
    clues that aired on the show (github.com/jwolle1/jeopardy_clue_dataset)
    into ~/.local/share/jtrainer/clues/. Each clue is shown with its air date.
    The clues belong to Jeopardy Productions, Inc.; keep them for your own
    study and do not republish them.

    Staying current: the game always starts from the newest clues it has
    (the last two years) and only reaches further back when a narrow seed
    runs out of categories you have not played. It also skips categories
    that rely on pictures, and categories with a clue that is likely to have
    gone out of date: time-sensitive wording ("current", "reigning", "this
    year"), records and rankings in clues over a year old ("all-time",
    "most populous"), and subjects that have changed since the clue aired
    (the British throne in 2022, the U.S. presidency in 2025, the papacy in
    2025 ...). Those filters are automatic guesses, not a guarantee: a clue
    was correct on the day it aired, and the air date on screen tells you
    how old it is.

    Whole categories about African geography are rare, so that seed also gets
    "AFRICA GEOGRAPHY MIX" categories: single clues whose correct response is
    an African place, taken from other geography categories. Each one shows
    the category and date it originally aired in.

    The built-in practice set (--practice, or when nothing is downloaded)
    is 378 clues written for this trainer in the show's style. They are NOT
    from the show.

    Your own clue files work too: --clues FILE_OR_FOLDER (TSV/CSV with the
    columns category, answer, question, and optionally round, clue_value,
    air_date, comments; or JSON with category/clue/response).
"""

import argparse
import csv
import glob
import hashlib
import html
import json
import os
import random
import re
import select
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unicodedata
from datetime import date

try:
    import readline  # noqa: F401  (gives input() line editing)
except ImportError:
    pass
try:
    import termios
except ImportError:
    termios = None

VERSION = "2.0"
ROUND1_VALUES = [200, 400, 600, 800, 1000]
ROUND2_VALUES = [400, 800, 1200, 1600, 2000]
USE_COLOR = False

# Where --fetch gets season files. {n} is the season number.
SOURCE_URL = os.environ.get(
    "JTRAINER_SOURCE",
    "https://raw.githubusercontent.com/jwolle1/jeopardy_clue_dataset/main/seasons/season{n}.tsv")
SOURCE_PAGE = "https://github.com/jwolle1/jeopardy_clue_dataset"
KNOWN_SEASON = 42            # newest season when this file was written (2025-26)
DEFAULT_FETCH = 6            # seasons downloaded by a plain --fetch
RECENT_YEARS = 2             # how far back a game looks before widening

# --------------------------------------------------------------------------
#  SEEDS (THEMES)
#  name:    a category whose name matches is a candidate for the theme
#  skip:    ...unless its name also matches this
#  content: ...and at least `need` of its 5 clues (text + response) match this
#  strong / weak: words that map free-text seeds onto the theme
# --------------------------------------------------------------------------
AFRICA_PLACES = (
    r"africa|algeria|angola|benin|botswana|burkina|burundi|cameroon|cape verde|cabo verde|"
    r"chad|comoros|congo|djibouti|egypt|guinea|eritrea|eswatini|swaziland|ethiopia|gabon|"
    r"gambia|ghana|ivory coast|cote d|kenya|lesotho|liberia|libya|madagascar|malawi|mali|"
    r"mauritania|mauritius|morocco|mozambique|namibia|niger|rwanda|sao tome|senegal|"
    r"seychelles|sierra leone|somalia|sudan|tanzania|togo|tunisia|uganda|zambia|zimbabwe|"
    r"sahara|sahel|nile|kilimanjaro|zambezi|limpopo|kalahari|namib|serengeti|victoria|"
    r"tanganyika|cairo|nairobi|lagos|accra|dakar|addis ababa|johannesburg|cape town|"
    r"casablanca|marrakech|tunis|algiers|tripoli|khartoum|kinshasa|zanzibar|timbuktu|atlas")
# Stricter list used to pull single Africa clues out of general geography categories:
# the clue's correct response has to be one of these places.
AFRICA_STRICT = re.compile(
    r"\b(africa|algeria|angola|benin|botswana|burkina faso|burundi|cameroon|cape verde|"
    r"cabo verde|chad|comoros|congo|djibouti|egypt|equatorial guinea|guinea-bissau|"
    r"(?<!new )guinea(?! pig)|eritrea|eswatini|swaziland|ethiopia|gabon|gambia|ghana|"
    r"ivory coast|cote d'ivoire|kenya|lesotho|liberia|libya|madagascar|malawi|mali|"
    r"mauritania|mauritius|morocco|mozambique|namibia|niger|nigeria|rwanda|sao tome|"
    r"senegal|seychelles|sierra leone|somalia|sudan|tanzania|togo|tunisia|uganda|zambia|"
    r"zimbabwe|zaire|rhodesia|abyssinia|"
    r"sahara|sahel|nile|kilimanjaro|zambezi|limpopo|kalahari|namib|serengeti|"
    r"lake victoria|victoria falls|tanganyika|lake chad|lake malawi|lake nasser|"
    r"lake turkana|okavango|suez canal|atlas mountains|cape of good hope|cape agulhas|"
    r"table mountain|mount kenya|great rift valley|gulf of guinea|zanzibar|reunion|"
    r"cairo|alexandria|giza|luxor|aswan|nairobi|mombasa|lagos|abuja|accra|dakar|"
    r"addis ababa|johannesburg|cape town|pretoria|durban|casablanca|marrakech|rabat|fez|"
    r"tangier|tunis|algiers|tripoli|khartoum|kinshasa|brazzaville|timbuktu|bamako|luanda|"
    r"lusaka|harare|maputo|windhoek|gaborone|kampala|kigali|abidjan|niamey|ouagadougou|"
    r"mogadishu|asmara|antananarivo|dar es salaam|dodoma|lilongwe|monrovia|freetown|"
    r"conakry|banjul|libreville|yaounde|juba|maseru|port louis)\b", re.I)
GEOGRAPHY_HOST = re.compile(
    r"\b(geograph\w*|capitals?|countr(y|ies)|nations?|cit(y|ies)|rivers?|lakes?|islands?|"
    r"mountains?|deserts?|maps?|borders?|continents?|bodies of water|landlocked|"
    r"national parks?|around the world)\b", re.I)
PRESIDENT_WORDS = (
    r"president|white house|first lady|veep|inaugur|oval office|washington|adams|jefferson|"
    r"madison|monroe|jackson|van buren|harrison|tyler|polk|taylor|fillmore|pierce|buchanan|"
    r"lincoln|johnson|grant|hayes|garfield|arthur|cleveland|mckinley|roosevelt|taft|wilson|"
    r"harding|coolidge|hoover|truman|eisenhower|kennedy|nixon|ford|carter|reagan|bush|"
    r"clinton|obama|trump|biden|fdr|jfk|lbj")

THEMES = {
    "africa": {
        "title": "Africa Geography",
        "strong": {"africa", "african"}, "weak": set(),
        "name": r"\bafrica|\bsahara\b",
        "skip": r"americ|histor|leader|cuisine|food|fiction|empire|author|writ|literat|"
                r"surname|people|animal|wildlife|mammal|queen|\bart\b|music|film|movie|proverb|"
                r"monarch|ruler|\bkings?\b",
        "content": r"\b(" + AFRICA_PLACES + r")", "need": 3,
        # Too few whole categories are about African geography, so this seed also
        # gets "mix" categories: single Africa clues from other geography categories.
        "mix": {"host": GEOGRAPHY_HOST, "clue": AFRICA_STRICT},
    },
    "water": {
        "title": "Bodies of Water",
        "strong": {"water", "waters", "rivers", "river", "lakes", "lake", "oceans", "ocean",
                   "seas", "sea"},
        "weak": {"bodies", "body"},
        "name": r"\b(bodies of water|rivers?|lakes?|seas?|oceans?|gulfs?|straits?|"
                r"waterfalls?|canals?|bays?|waterways?)\b",
        "skip": r"scroll|aquarium|lotion|beyond|change|tune|sea life|creature|animal|fish|"
                r"food|monster|packers|pigs|phoenix|joan|lake city|lakers|show|sky|battle|"
                r"navy|ships?\b|pirate|songs?\b|movie|film|\btv\b|book|novel|\blit\b|poe[mt]|"
                r"shanty|shanties|root canal|alimentary|green bay|bay of pigs",
        "content": r"\b(rivers?|lakes?|seas?|oceans?|bays?|gulfs?|straits?|canals?|falls|"
                   r"waterfalls?|channel|delta|lagoon|reservoir|fjords?|loch|tributar\w+|"
                   r"flows?|waters?|estuary|harbou?r|sound|atlantic|pacific)\b", "need": 3,
    },
    "presidents": {
        "title": "Presidents of the USA",
        "strong": {"presidents", "president", "presidential", "potus"},
        "weak": {"usa", "us"},
        "name": r"\b(presidents?|presidential|white house|first lad(y|ies)|veeps?|potus|"
                r"oval office|commander.in.chief)\b",
        "skip": r"female|women|not a president|college|universit|world|foreign|club|class\b|"
                r"compan|corporat|french|france|mexic|russia|latin|africa|south america|"
                r"europe|asia|confedera|fictional|movie|film|\btv\b",
        "content": r"\b(" + PRESIDENT_WORDS + r")", "need": 3,
    },
    "shakespeare": {
        "title": "Shakespeare",
        "strong": {"shakespeare", "shakespearean", "bard"}, "weak": set(),
        "name": r"shakespear|\bbard\b",
        "skip": r"ain't|isn't|not shakespeare|contemporar|bard college",
        "content": None, "need": 0,
    },
    "popculture": {
        "title": "Pop Culture",
        "strong": {"culture", "popculture", "tv", "television", "movies", "movie", "film",
                   "films"},
        "weak": {"pop"},
        "name": r"\b(pop culture|tv|television|movies?|films?|sitcoms?|hollywood|oscars?|"
                r"emmys?|celebrit\w+|celebs?|video games?|streaming|netflix|cartoons?|"
                r"animated|animation|superhero\w*|marvel|pixar|disney|game shows?|actors?|"
                r"actress\w*|blockbusters?|box office|binge\w*|memes?|podcasts?|"
                r"social media|star wars|snl|saturday night live|comedians?|talk shows?|"
                r"late night|soap operas?|sequels?|franchises?|cinema|on screen|the screen)\b",
        "skip": r"oscar wilde|oscar de la|film on|actors studio",
        "content": None, "need": 0,
    },
    "music": {
        "title": "Music",
        "strong": {"music", "musical", "songs", "song"}, "weak": set(),
        "name": r"\b(music\w*|songs?|singers?|bands?|operas?|composers?|albums?|grammys?|"
                r"jazz|hip.hop|rap|rappers?|broadway|lyrics?|rock (& |'n' |and )?roll|"
                r"rock (music|bands?|stars?|songs?|groups?)|classic rock|rockers?|"
                r"pop (stars?|hits|charts?)|country (stars?|hits)|r&b|symphon\w+|"
                r"orchestra\w*|billboard|top 40|duets?|divas?|guitar\w*|pianists?|beatles|"
                r"motown|reggae|k-pop|soundtracks?|songwriters?|choirs?)\b",
        "skip": r"soap opera|rap sheet|band of|song of (solomon|roland|hiawatha|myself)|"
                r"innocence|rubber band|wedding band|band-aid|songbird|song birds|"
                r"bandwidth|rock band names",
        "content": None, "need": 0,
    },
}
for _info in THEMES.values():
    _info["name"] = re.compile(_info["name"], re.I)
    _info["skip"] = re.compile(_info["skip"], re.I)
    if _info["content"]:
        _info["content"] = re.compile(_info["content"], re.I)

# Categories that cannot be played as text, and wording that dates a clue.
UNPLAYABLE_RE = re.compile(r"\bpicture the\b|\bpictures$|\brebus|\bemoji", re.I)
MEDIA_RE = re.compile(r"seen here|heard here|shown here|pictured here|here's a picture|"
                      r"clue crew|video clue", re.I)
STALE_RE = re.compile(
    r"\b(currently|current|reigning|incumbent|newest|latest|most recent|recently|"
    r"this year|last year|next year|this month|last month|so far|to date|upcoming|"
    r"as of (this|20\d\d)|still (the|holds|reigns|serves|serving)|"
    r"now (the|holds|serves|serving|hosts|ranks))\b", re.I)
STALE_HINTS = ("current", "reigning", "incumbent", "newest", "latest", "recent", " year",
               " month", "so far", "to date", "upcoming", "as of", "still ", "now ")
# Records and rankings that get overtaken: skipped once a clue is over a year old.
VOLATILE_RE = re.compile(
    r"\b(most populous|most populated|all-time|world record|holds the record|record[- ]holder|"
    r"record for (the )?most|highest-grossing|top-grossing|richest|wealthiest|winningest|"
    r"longest-(serving|reigning|running)|oldest living|last (surviving|living)|"
    r"only (u\.s\. |american )?president|living (former |ex-)?presidents?|"
    r"most (grammys|oscars|emmys|tonys|wins|titles|medals|championships|home runs|goals|"
    r"points|followers|subscribers|streams|streamed|viewed|watched)|"
    r"tallest (building|structure|skyscraper|tower)|busiest|"
    r"largest (company|economy|employer)|biggest (company|economy)|"
    r"newest (country|nation|state|member)|"
    r"youngest (ever|person|player|winner|president|country|nation))\b", re.I)
VOLATILE_HINTS = ("most ", "all-time", "record", "grossing", "richest", "wealthiest",
                  "winningest", "longest-", "living", "tallest", "busiest", "largest ",
                  "biggest ", "newest ", "youngest ", "only ")
CHANGE_HINTS = ("facebook", "elizabeth", "prince", "duke of", "duchess", "british", "heir to",
                "succession", "nur-sultan", "jabbar", "scor", "population", "more people",
                "twitter", "tweet", "carter", "consecutive", "biden", "harris", "trump",
                "oldest", "45 ", "46 ", "gentleman", "pope", "pontiff", "papa")
# Things that changed: a clue that aired before the date and touches the subject is skipped.
WORLD_CHANGES = [(day, re.compile(pattern, re.I)) for day, pattern in (
    ("2021-10-28", r"\bfacebook\b"),                        # company renamed Meta
    ("2022-09-08", r"queen elizabeth|elizabeth ii|prince charles|prince of wales|"
                   r"duke of cambridge|duchess of cornwall|british (monarch|throne)|"
                   r"heir to the (british )?throne|line of succession"),
    ("2022-09-17", r"nur-sultan"),                           # capital renamed Astana
    ("2023-02-07", r"abdul-jabbar|scoring (record|leader)|leading scorer"),
    ("2023-04-30", r"largest population|more people than"),  # India passed China
    ("2023-07-24", r"\btwitter\b|\btweets?\b"),             # renamed X
    ("2024-12-29", r"jimmy carter|president carter"),
    ("2025-01-20", r"non-?consecutive|president biden|vice president harris|"
                   r"(former|ex-)president trump|oldest (u\.s\. )?president|"
                   r"oldest (person|man) (ever )?(to be|to become|to serve|elected|inaugurated)|"
                   r"\b4[56] (men|people|presidents)\b|second gentleman"),
    ("2025-05-08", r"\bpopes?\b|pontiff|papacy|papal"),      # Leo XIV elected
)]
MEDIA_HINTS = (" here", "here's", "clue crew", "video")
TAG_RE = re.compile(r"<[^>]+>")

# --------------------------------------------------------------------------
#  BUILT-IN PRACTICE SET (written for this trainer - not from the show)
#  Each clue: (clue text, correct response, *other accepted answers)
#  Five clues per category, easiest first.
# --------------------------------------------------------------------------
JFK = ("Who is John F. Kennedy?", "kennedy", "jfk", "john kennedy", "jack kennedy",
       "john fitzgerald kennedy")
FDR = ("Who is Franklin D. Roosevelt?", "fdr", "franklin roosevelt",
       "franklin delano roosevelt")
TEDDY = ("Who is Theodore Roosevelt?", "teddy roosevelt", "tr", "t roosevelt")
REAGAN = ("Who is Ronald Reagan?", "reagan", "ronald wilson reagan")
IKE = ("Who is Dwight D. Eisenhower?", "eisenhower", "dwight eisenhower", "ike")

BANK = {
    # ===================================================== AFRICA GEOGRAPHY
    "africa": [
        ("AFRICAN CAPITALS", [
            ("Pretoria, Cape Town & Bloemfontein all serve as capitals of this country",
             "What is South Africa?", "republic of south africa"),
            ("Kampala, near the northern shore of Lake Victoria, is the capital of this country",
             "What is Uganda?"),
            ("Dakar, on the Cap-Vert peninsula at mainland Africa's western tip, is this country's capital",
             "What is Senegal?"),
            ("Kigali is the capital of this nation nicknamed the \"Land of a Thousand Hills\"",
             "What is Rwanda?"),
            ("Ouagadougou is the capital of this landlocked country known as Upper Volta until 1984",
             "What is Burkina Faso?", "burkina"),
        ]),
        ("RIVERS OF AFRICA", [
            ("Generally ranked the world's longest river, it flows north through Sudan & Egypt to the Mediterranean",
             "What is the Nile?", "nile river", "river nile"),
            ("Africa's second-longest river shares its name with the 2 countries whose capitals face each other across it",
             "What is the Congo?", "congo river", "zaire river"),
            ("This river tumbles over Victoria Falls on the border of Zambia & Zimbabwe",
             "What is the Zambezi?", "zambezi river", "zambesi", "zambesi river"),
            ("Rising in the highlands of Guinea, this West African river flows past Bamako & Niamey on its way to the Gulf of Guinea",
             "What is the Niger?", "niger river"),
            ("Kipling called this river on South Africa's northern border \"great grey-green, greasy\"",
             "What is the Limpopo?", "limpopo river"),
        ]),
        ("LAKES OF AFRICA", [
            ("Africa's largest lake by area, it was named for a British queen by explorer John Hanning Speke",
             "What is Lake Victoria?", "victoria", "victoria nyanza"),
            ("This drastically shrunken lake gave its name to the country whose capital is N'Djamena",
             "What is Lake Chad?", "chad"),
            ("Lake Nasser was created when this dam was built across the Nile in the 1960s",
             "What is the Aswan High Dam?", "aswan dam", "aswan", "high dam"),
            ("The world's longest freshwater lake, it lent its name to the mainland territory that united with Zanzibar in 1964",
             "What is Lake Tanganyika?", "tanganyika"),
            ("Once called Lake Rudolf, this lake in northern Kenya is the world's largest permanent desert lake",
             "What is Lake Turkana?", "turkana"),
        ]),
        ("DESERTS & MOUNTAINS", [
            ("Stretching across North Africa, it's the world's largest hot desert",
             "What is the Sahara?", "sahara desert"),
            ("At 19,341 feet, this dormant volcano in Tanzania is Africa's highest peak",
             "What is Mount Kilimanjaro?", "kilimanjaro", "mt kilimanjaro"),
            ("The San people have long lived in this semi-arid expanse that covers most of Botswana",
             "What is the Kalahari?", "kalahari desert"),
            ("Named for a Titan, this mountain range runs through Morocco, Algeria & Tunisia",
             "What are the Atlas Mountains?", "atlas", "atlas range"),
            ("The towering red dunes of Sossusvlei rise in this coastal desert, often called the world's oldest",
             "What is the Namib?", "namib desert"),
        ]),
        ("ISLANDS OF AFRICA", [
            ("Lemurs are native only to this island, the world's fourth largest",
             "What is Madagascar?"),
            ("This Tanzanian archipelago, long a hub of the clove trade, was once ruled by the sultans of Oman",
             "What is Zanzibar?"),
            ("Nelson Mandela spent 18 of his 27 years in prison on this island off Cape Town",
             "What is Robben Island?", "robben"),
            ("The flightless dodo lived only on this Indian Ocean island nation whose capital is Port Louis",
             "What is Mauritius?"),
            ("Praia is the capital of this island nation in the Atlantic, about 350 miles off the coast of Senegal",
             "What is Cape Verde?", "cabo verde"),
        ]),
        ("NORTH AFRICA", [
            ("The Suez Canal crosses this country, linking the Mediterranean & Red Seas",
             "What is Egypt?"),
            ("Casablanca & Marrakech are major cities in this kingdom",
             "What is Morocco?"),
            ("The ruins of ancient Carthage lie on the outskirts of this North African capital",
             "What is Tunis?"),
            ("Leptis Magna, among the best-preserved Roman cities anywhere, lies on this country's coast east of Tripoli",
             "What is Libya?"),
            ("The old citadel quarter of this capital on the Mediterranean is known as the Casbah",
             "What is Algiers?"),
        ]),
        ("WEST AFRICA", [
            ("In 1957 the British colony called the Gold Coast became this independent nation",
             "What is Ghana?"),
            ("Founded as a home for freed American slaves, it named its capital Monrovia for a U.S. president",
             "What is Liberia?"),
            ("Abidjan is the largest city of this country, the world's leading producer of cocoa",
             "What is Ivory Coast?", "cote divoire", "cote d ivoire"),
            ("The fabled trading & scholarly city of Timbuktu is in this landlocked country",
             "What is Mali?"),
            ("Mainland Africa's smallest country, it follows its namesake river & is nearly surrounded by Senegal",
             "What is The Gambia?", "gambia"),
        ]),
        ("EAST AFRICA", [
            ("Serengeti National Park & Mount Kilimanjaro are both in this country",
             "What is Tanzania?"),
            ("The Maasai Mara reserve & the port of Mombasa are in this country that straddles the Equator",
             "What is Kenya?"),
            ("The rock-hewn churches of Lalibela are in this country, long known to outsiders as Abyssinia",
             "What is Ethiopia?"),
            ("This country on the Horn of Africa has the longest coastline on the African mainland",
             "What is Somalia?"),
            ("With its capital at Asmara, this Red Sea country won independence from Ethiopia in 1993",
             "What is Eritrea?"),
        ]),
        ("SOUTHERN AFRICA", [
            ("Flat-topped Table Mountain looms over this South African city",
             "What is Cape Town?", "capetown"),
            ("The Okavango Delta is in this country whose capital is Gaborone",
             "What is Botswana?"),
            ("This mountain kingdom is completely surrounded by South Africa",
             "What is Lesotho?"),
            ("Maputo is the capital of this Portuguese-speaking country on the Indian Ocean",
             "What is Mozambique?"),
            ("Not the Cape of Good Hope but this cape is the southernmost point of Africa",
             "What is Cape Agulhas?", "agulhas"),
        ]),
        ("FORMERLY KNOWN AS", [
            ("Southern Rhodesia, later just Rhodesia, became this nation in 1980",
             "What is Zimbabwe?"),
            ("From 1971 to 1997, the Democratic Republic of the Congo went by this name",
             "What is Zaire?"),
            ("In 2018 King Mswati III announced that Swaziland would henceforth be called this",
             "What is Eswatini?", "kingdom of eswatini"),
            ("The British protectorate of Nyasaland became this independent country in 1964",
             "What is Malawi?"),
            ("Known as Dahomey until 1975, this West African country borders Nigeria & Togo",
             "What is Benin?"),
        ]),
        ("AFRICAN SUPERLATIVES", [
            ("With well over 200 million people, it's Africa's most populous country",
             "What is Nigeria?"),
            ("Since Sudan was divided in 2011, this has been Africa's largest country by area",
             "What is Algeria?"),
            ("Africa's newest country, it became independent in July 2011 with its capital at Juba",
             "What is South Sudan?"),
            ("This Indian Ocean archipelago is Africa's smallest country in both area & population",
             "What is Seychelles?", "the seychelles"),
            ("Lake Assal, Africa's lowest point at more than 500 feet below sea level, is in this small country on the Horn",
             "What is Djibouti?"),
        ]),
        ("AFRICAN CITIES", [
            ("The Great Sphinx & the Pyramids of Giza stand on the edge of this capital, the largest city in the Arab world",
             "What is Cairo?"),
            ("Nicknamed Jo'burg & Jozi, this is South Africa's largest city",
             "What is Johannesburg?", "joburg"),
            ("Founded by a Macedonian conqueror in 331 B.C., this Egyptian port was famed for its library & its lighthouse",
             "What is Alexandria?"),
            ("Brazzaville sits directly across the Congo River from this much larger capital",
             "What is Kinshasa?"),
            ("A brimless, tasseled felt hat shares its name with this old Moroccan city",
             "What is Fez?", "fes"),
        ]),
    ],

    # ====================================================== BODIES OF WATER
    "water": [
        ("OCEANS", [
            ("It's the largest & deepest of Earth's oceans",
             "What is the Pacific?", "pacific ocean"),
            ("It's the only ocean named for a country",
             "What is the Indian Ocean?", "indian"),
            ("The smallest & shallowest ocean, it surrounds the North Pole",
             "What is the Arctic Ocean?", "arctic"),
            ("The Challenger Deep, the deepest known point in any ocean, lies in this Pacific trench",
             "What is the Mariana Trench?", "marianas trench", "mariana", "marianas"),
            ("In 2021 National Geographic began recognizing this body of water encircling Antarctica as the world's fifth ocean",
             "What is the Southern Ocean?", "southern", "antarctic ocean"),
        ]),
        ("SEAS", [
            ("Bathers float effortlessly in this super-salty lake between Israel & Jordan, whose shore is Earth's lowest land elevation",
             "What is the Dead Sea?"),
            ("In Exodus, Moses parts this sea that separates Africa from the Arabian Peninsula",
             "What is the Red Sea?"),
            ("The world's largest inland body of water, it's bordered by Russia, Kazakhstan, Turkmenistan, Iran & Azerbaijan",
             "What is the Caspian Sea?", "caspian"),
            ("The Bosporus links the Sea of Marmara with this sea to the north",
             "What is the Black Sea?"),
            ("Named for its floating seaweed, this sea in the North Atlantic is bounded by ocean currents instead of land",
             "What is the Sargasso Sea?", "sargasso"),
        ]),
        ("WORLD RIVERS", [
            ("By volume of water carried, this South American river is by far the world's largest",
             "What is the Amazon?", "amazon river"),
            ("Hindus revere this river of northern India as the goddess Ganga",
             "What is the Ganges?", "ganges river"),
            ("Spanned by the Three Gorges Dam, it's the longest river in Asia",
             "What is the Yangtze?", "yangtze river", "yangzi", "yangtse", "chang jiang"),
            ("This Southeast Asian river forms much of the Laos-Thailand border before fanning into a delta in southern Vietnam",
             "What is the Mekong?", "mekong river"),
            ("The Tigris joins this river in southern Iraq to form the Shatt al-Arab",
             "What is the Euphrates?", "euphrates river"),
        ]),
        ("U.S. RIVERS", [
            ("Mark Twain piloted steamboats on this river, the setting for much of \"Huckleberry Finn\"",
             "What is the Mississippi?", "mississippi river"),
            ("Over millions of years this river carved the Grand Canyon",
             "What is the Colorado?", "colorado river"),
            ("This river forms the entire border between Texas & Mexico",
             "What is the Rio Grande?", "rio grande river", "rio bravo"),
            ("The longest river in the United States, it joins the Mississippi just north of St. Louis",
             "What is the Missouri?", "missouri river"),
            ("Lewis & Clark reached the Pacific at the mouth of this river, which forms much of the Oregon-Washington border",
             "What is the Columbia?", "columbia river"),
        ]),
        ("LAKES OF THE WORLD", [
            ("A legendary monster nicknamed Nessie is said to lurk in this Scottish lake",
             "What is Loch Ness?", "ness", "lake ness"),
            ("This remnant of ancient Lake Bonneville in Utah is far saltier than the ocean",
             "What is the Great Salt Lake?", "great salt"),
            ("This Siberian lake is the world's deepest & holds about a fifth of Earth's unfrozen fresh surface water",
             "What is Lake Baikal?", "baikal"),
            ("Straddling the border of Peru & Bolivia, it's called the world's highest navigable lake",
             "What is Lake Titicaca?", "titicaca"),
            ("Filling the caldera of collapsed Mount Mazama, this Oregon lake is the deepest in the U.S.",
             "What is Crater Lake?", "crater"),
        ]),
        ("THE GREAT LAKES", [
            ("The largest Great Lake, it's also the world's largest freshwater lake by surface area",
             "What is Lake Superior?", "superior"),
            ("It's the only Great Lake that lies entirely within the United States",
             "What is Lake Michigan?", "michigan"),
            ("Cleveland & Buffalo sit on this shallowest of the Great Lakes",
             "What is Lake Erie?", "erie"),
            ("Toronto lies on the shore of this Great Lake, the smallest in surface area",
             "What is Lake Ontario?", "ontario"),
            ("Manitoulin, the world's largest island in a freshwater lake, is in this Great Lake",
             "What is Lake Huron?", "huron"),
        ]),
        ("STRAITS & CHANNELS", [
            ("The \"Chunnel\" rail tunnel runs beneath this body of water between England & France",
             "What is the English Channel?", "channel", "la manche"),
            ("About 8 miles wide at its narrowest, this strait separates Spain from Morocco",
             "What is the Strait of Gibraltar?", "gibraltar", "straits of gibraltar"),
            ("Named for a Danish navigator who sailed for Russia, this strait separates Alaska from Siberia",
             "What is the Bering Strait?", "bering"),
            ("This strait between Iran & Oman is the only sea passage from the Persian Gulf to the open ocean",
             "What is the Strait of Hormuz?", "hormuz", "straits of hormuz"),
            ("Known to the ancient Greeks as the Hellespont, this Turkish strait links the Aegean to the Sea of Marmara",
             "What are the Dardanelles?", "dardanelles strait", "dardanelle"),
        ]),
        ("GULFS & BAYS", [
            ("The Golden Gate Bridge spans the strait at the entrance to this California bay",
             "What is San Francisco Bay?", "san francisco", "sf bay"),
            ("This vast bay in northern Canada shares its name with a fur-trading company chartered in 1670",
             "What is Hudson Bay?", "hudson", "hudsons bay"),
            ("Bordered by Maryland & Virginia, it's the largest estuary in the United States",
             "What is Chesapeake Bay?", "chesapeake"),
            ("This bay between New Brunswick & Nova Scotia is famed for the highest tides on Earth",
             "What is the Bay of Fundy?", "fundy"),
            ("The Ganges & Brahmaputra empty into this bay, the largest in the world",
             "What is the Bay of Bengal?", "bengal"),
        ]),
        ("CANALS", [
            ("Opened in 1914, this canal lets ships cross between the Atlantic & Pacific without rounding South America",
             "What is the Panama Canal?", "panama"),
            ("Opened in 1869, this Egyptian canal connects the Mediterranean with the Red Sea",
             "What is the Suez Canal?", "suez"),
            ("Completed in 1825, this New York canal linked the Hudson River with the Great Lakes at Buffalo",
             "What is the Erie Canal?", "erie"),
            ("Gondolas glide beneath the Rialto Bridge on this main waterway of Venice",
             "What is the Grand Canal?", "canal grande", "canale grande"),
            ("This German canal, one of the world's busiest artificial waterways, links the North Sea with the Baltic",
             "What is the Kiel Canal?", "kiel", "nord ostsee kanal"),
        ]),
        ("WATERFALLS", [
            ("Horseshoe Falls is the largest of the 3 cataracts that make up this landmark on the U.S.-Canada border",
             "What is Niagara Falls?", "niagara"),
            ("At 3,212 feet, this Venezuelan waterfall named for an American aviator is the world's tallest",
             "What is Angel Falls?", "angel", "salto angel", "kerepakupai meru"),
            ("On the Zambezi River, this waterfall is known locally as Mosi-oa-Tunya, \"The Smoke That Thunders\"",
             "What is Victoria Falls?", "victoria"),
            ("Some 275 separate cascades make up these falls on the border of Brazil & Argentina",
             "What are Iguazu Falls?", "iguazu", "iguacu", "iguassu", "iguacu falls", "iguassu falls"),
            ("A 2,425-foot waterfall shares its name with this California national park, also home to El Capitan",
             "What is Yosemite?", "yosemite national park", "yosemite falls"),
        ]),
        ("EUROPEAN RIVERS", [
            ("Tower Bridge & London Bridge both cross this river",
             "What is the Thames?", "river thames", "thames river"),
            ("Notre-Dame Cathedral stands on an island in this river",
             "What is the Seine?", "seine river", "river seine"),
            ("A Strauss waltz calls it \"beautiful\" & \"blue\"; it flows through Vienna, Budapest & Belgrade",
             "What is the Danube?", "danube river", "donau"),
            ("Europe's longest river, it flows through Russia to the Caspian Sea",
             "What is the Volga?", "volga river"),
            ("The Ponte Vecchio spans this river in Florence",
             "What is the Arno?", "arno river"),
        ]),
        ("SEAS THE DAY", [
            ("Though called a sea, this body of water in Israel where the Gospels say Jesus walked on water is a freshwater lake",
             "What is the Sea of Galilee?", "galilee", "lake tiberias", "kinneret", "lake kinneret"),
            ("The Great Barrier Reef lies in this aptly named sea off the coast of Queensland",
             "What is the Coral Sea?", "coral"),
            ("Once the world's fourth-largest lake, this Central Asian \"sea\" has largely dried up since its rivers were diverted for irrigation",
             "What is the Aral Sea?", "aral"),
            ("Venice, Split & Dubrovnik all lie on this arm of the Mediterranean",
             "What is the Adriatic Sea?", "adriatic"),
            ("This sea separating Australia from New Zealand is named for a 17th-century Dutch explorer",
             "What is the Tasman Sea?", "tasman"),
        ]),
    ],

    # ================================================ PRESIDENTS OF THE USA
    "presidents": [
        ("PRESIDENTIAL FIRSTS", [
            ("The first president, he's the only one to have been elected unanimously by the Electoral College",
             "Who is George Washington?", "washington"),
            ("In 1974 he became the first president to resign from office",
             "Who is Richard Nixon?", "nixon", "richard m nixon", "richard milhous nixon"),
            ("In 1961 he became the first Roman Catholic president",) + JFK,
            ("In 1868 he became the first president to be impeached by the House",
             "Who is Andrew Johnson?"),
            ("Born in Kinderhook, New York in 1782, he was the first president born a U.S. citizen",
             "Who is Martin Van Buren?", "van buren"),
        ]),
        ("FOUNDING PRESIDENTS", [
            ("The third president, he was the principal author of the Declaration of Independence",
             "Who is Thomas Jefferson?", "jefferson"),
            ("Called the \"Father of the Constitution\", he was president during the War of 1812",
             "Who is James Madison?", "madison"),
            ("His 1823 doctrine warned European powers against new colonization in the Americas",
             "Who is James Monroe?", "monroe"),
            ("The son of the second president, this sixth president later served 17 years in the House of Representatives",
             "Who is John Quincy Adams?", "john q adams", "jqa", "quincy adams"),
            ("He & Thomas Jefferson both died on July 4, 1826, the 50th anniversary of the Declaration of Independence",
             "Who is John Adams?"),
        ]),
        ("19th CENTURY PRESIDENTS", [
            ("Known as \"Old Hickory\", this seventh president was the hero of the Battle of New Orleans",
             "Who is Andrew Jackson?", "jackson"),
            ("This Union general accepted Lee's surrender at Appomattox & later served 2 terms as president",
             "Who is Ulysses S. Grant?", "grant", "ulysses grant", "u s grant"),
            ("Counted as both the 22nd & 24th president, he was the first to serve nonconsecutive terms",
             "Who is Grover Cleveland?", "cleveland"),
            ("Under this 11th president, nicknamed \"Young Hickory\", victory in the Mexican-American War added California & the Southwest",
             "Who is James K. Polk?", "polk", "james polk", "james knox polk"),
            ("Inaugurated in March 1841, he died just 31 days into his term",
             "Who is William Henry Harrison?", "william harrison", "w h harrison"),
        ]),
        ("20th CENTURY PRESIDENTS", [
            ("He's the only president to have been elected 4 times",) + FDR,
            ("A former president of Princeton University, he led the U.S. through World War I & championed the League of Nations",
             "Who is Woodrow Wilson?", "wilson"),
            ("A sign on his desk read \"The buck stops here\"; he ordered the atomic bombings of Japan in 1945",
             "Who is Harry S. Truman?", "truman", "harry truman"),
            ("Once Supreme Allied Commander in Europe, as president he signed the 1956 act creating the Interstate Highway System",) + IKE,
            ("After leaving the White House, he became the only ex-president to serve as Chief Justice of the United States",
             "Who is William Howard Taft?", "taft", "william taft", "william h taft"),
        ]),
        ("RECENT PRESIDENTIAL HISTORY", [
            ("Inaugurated in 2009, he was the first African American president",
             "Who is Barack Obama?", "obama", "barack h obama", "barack hussein obama"),
            ("Sworn in as the 47th president in January 2025, he's the second president to serve nonconsecutive terms",
             "Who is Donald Trump?", "trump", "donald j trump", "donald john trump"),
            ("The longest-lived president in U.S. history, this 39th president died in December 2024 at age 100",
             "Who is Jimmy Carter?", "carter", "james carter", "james earl carter"),
            ("George W. Bush won the 2000 election after the Supreme Court halted a recount in this state by a 5-4 vote",
             "What is Florida?"),
            ("Before serving as vice president & then president, Joe Biden represented this state in the Senate for 36 years",
             "What is Delaware?"),
        ]),
        ("PRESIDENTIAL NICKNAMES", [
            ("\"Honest Abe\" & \"The Rail-Splitter\"",
             "Who is Abraham Lincoln?", "lincoln", "abe lincoln"),
            ("\"The Rough Rider\" & \"The Trust Buster\"",) + TEDDY,
            ("\"Silent Cal\"",
             "Who is Calvin Coolidge?", "coolidge"),
            ("\"Old Rough and Ready\", a hero of the Mexican-American War",
             "Who is Zachary Taylor?", "taylor"),
            ("\"His Accidency\", so called after he succeeded William Henry Harrison in 1841",
             "Who is John Tyler?", "tyler"),
        ]),
        ("VICE PRESIDENTS", [
            ("In 2021 she became the first woman to serve as vice president",
             "Who is Kamala Harris?", "harris", "kamala d harris"),
            ("This Ohio senator & author of \"Hillbilly Elegy\" became vice president in January 2025",
             "Who is JD Vance?", "vance", "j d vance", "james david vance"),
            ("Thomas Jefferson's first vice president, he mortally wounded Alexander Hamilton in an 1804 duel",
             "Who is Aaron Burr?", "burr"),
            ("He's the only person to serve as both vice president & president without being elected to either office",
             "Who is Gerald Ford?", "ford", "gerald r ford", "jerry ford"),
            ("Richard Nixon's first vice president, he resigned in 1973 & pleaded no contest to tax evasion",
             "Who is Spiro Agnew?", "agnew", "spiro t agnew"),
        ]),
        ("FIRST LADIES", [
            ("Five years after her husband's assassination, she married Greek shipping magnate Aristotle Onassis",
             "Who is Jacqueline Kennedy?", "jackie kennedy", "jacqueline kennedy onassis",
             "jackie kennedy onassis", "jackie onassis", "jackie o", "jacqueline onassis",
             "jacqueline bouvier kennedy"),
            ("First lady from 2009 to 2017, she wrote the bestselling memoir \"Becoming\"",
             "Who is Michelle Obama?"),
            ("As the British advanced on Washington in 1814, she saw to it that a portrait of George Washington was saved",
             "Who is Dolley Madison?", "dolly madison"),
            ("The longest-serving first lady, she later chaired the U.N. commission that drafted the Universal Declaration of Human Rights",
             "Who is Eleanor Roosevelt?"),
            ("She & Barbara Bush are the only 2 women to have been both the wife & the mother of a president",
             "Who is Abigail Adams?"),
        ]),
        ("BEFORE THEY WERE PRESIDENT", [
            ("This future 40th president acted in Hollywood films including \"Knute Rockne, All American\"",) + REAGAN,
            ("A Rhodes Scholar, he was elected governor of Arkansas 5 times",
             "Who is Bill Clinton?", "clinton", "william jefferson clinton", "william clinton"),
            ("He was managing partner of baseball's Texas Rangers before becoming governor of Texas",
             "Who is George W. Bush?", "george walker bush", "bush 43", "w", "dubya", "george bush jr"),
            ("His resume included U.N. ambassador, envoy to China & director of the CIA",
             "Who is George H.W. Bush?", "george herbert walker bush", "bush 41",
             "george bush sr", "bush sr", "george bush senior"),
            ("A mining engineer by training, he won fame leading food relief for Belgium during World War I",
             "Who is Herbert Hoover?", "hoover"),
        ]),
        ("PRESIDENTIAL QUOTES", [
            ("\"Ask not what your country can do for you--ask what you can do for your country\"",) + JFK,
            ("\"Mr. Gorbachev, tear down this wall!\"",) + REAGAN,
            ("\"The only thing we have to fear is fear itself\"",) + FDR,
            ("\"Speak softly and carry a big stick\" was a favorite proverb of this president",) + TEDDY,
            ("In his 1961 farewell address, he warned against the influence of the \"military-industrial complex\"",) + IKE,
        ]),
        ("DEATH OF A PRESIDENT", [
            ("This actor shot Abraham Lincoln at Ford's Theatre on April 14, 1865",
             "Who is John Wilkes Booth?", "booth", "john booth"),
            ("President Kennedy was assassinated in this Texas city on November 22, 1963",
             "What is Dallas?"),
            ("Shot at the 1901 Pan-American Exposition in Buffalo, he was succeeded by Theodore Roosevelt",
             "Who is William McKinley?", "mckinley"),
            ("Shot by Charles Guiteau in July 1881, this president lingered for 11 weeks before dying",
             "Who is James A. Garfield?", "garfield", "james garfield"),
            ("He died in a San Francisco hotel in 1923, as the Teapot Dome scandal was beginning to surface",
             "Who is Warren G. Harding?", "harding", "warren harding"),
        ]),
        ("PRESIDENTIAL PLACES", [
            ("It's George Washington's estate overlooking the Potomac River",
             "What is Mount Vernon?", "mt vernon"),
            ("Thomas Jefferson designed this Virginia home, pictured on the back of the nickel",
             "What is Monticello?"),
            ("Mount Rushmore, with its 4 presidential faces, is in this state",
             "What is South Dakota?"),
            ("President Eisenhower renamed the Maryland retreat \"Shangri-La\" this, in honor of his grandson",
             "What is Camp David?"),
            ("Andrew Jackson is buried at this plantation home of his near Nashville",
             "What is The Hermitage?", "hermitage"),
        ]),
    ],

    # ========================================================== SHAKESPEARE
    "shakespeare": [
        ("SHAKESPEAREAN TRAGEDIES", [
            ("The feuding Montagues & Capulets doom a pair of \"star-cross'd lovers\" in this tragedy",
             "What is Romeo and Juliet?", "romeo juliet"),
            ("Three witches prophesy that this Scottish general will be king",
             "Who is Macbeth?"),
            ("This Moorish general in the service of Venice is tricked into believing his wife, Desdemona, has been unfaithful",
             "Who is Othello?"),
            ("He divides his kingdom between daughters Goneril & Regan & disowns the loyal Cordelia",
             "Who is King Lear?", "lear"),
            ("Banished from Rome, this proud general joins the Volscians to march against his own city",
             "Who is Coriolanus?", "caius martius", "caius marcius coriolanus"),
        ]),
        ("SHAKESPEAREAN COMEDIES", [
            ("Puck's mischief & Bottom's donkey head enliven this comedy set in an enchanted wood",
             "What is A Midsummer Night's Dream?", "midsummer"),
            ("Petruchio sets out to woo & \"tame\" the sharp-tongued Katherina in this comedy",
             "What is The Taming of the Shrew?", "taming of shrew"),
            ("Beatrice & Benedick trade barbs before falling in love in this comedy set in Messina",
             "What is Much Ado About Nothing?", "much ado"),
            ("Shipwrecked Viola disguises herself as a young man named Cesario in this comedy named for a holiday",
             "What is Twelfth Night?", "12th night", "twelfth night or what you will"),
            ("Twin masters both named Antipholus & twin servants both named Dromio cause chaos in this, Shakespeare's shortest play",
             "What is The Comedy of Errors?", "comedy of errors"),
        ]),
        ("THE HISTORY PLAYS", [
            ("\"A horse! a horse! my kingdom for a horse!\" cries this title king at Bosworth Field",
             "Who is Richard III?", "richard 3", "richard the third", "richard the 3rd"),
            ("Before the Battle of Agincourt, this king rallies his outnumbered \"band of brothers\"",
             "Who is Henry V?", "henry 5", "henry the fifth", "henry the 5th"),
            ("This fat, witty knight carouses with Prince Hal at the Boar's Head Tavern",
             "Who is Falstaff?", "john falstaff"),
            ("In \"Henry IV, Part 1\", the fiery rebel Harry Percy is better known by this nickname",
             "What is Hotspur?"),
            ("A cannon fired during a 1613 performance of this history play sparked the fire that destroyed Shakespeare's original playhouse",
             "What is Henry VIII?", "henry 8", "henry the eighth", "henry the 8th", "all is true"),
        ]),
        ("WHO'S WHO IN SHAKESPEARE", [
            ("Hamlet's doomed sweetheart, she goes mad & drowns in a brook",
             "Who is Ophelia?"),
            ("In \"The Merchant of Venice\", this moneylender demands a pound of flesh as his bond",
             "Who is Shylock?"),
            ("Slain by Tybalt, this friend of Romeo gasps, \"A plague o' both your houses!\"",
             "Who is Mercutio?"),
            ("Disguised as a doctor of law, this heiress delivers the \"quality of mercy\" speech",
             "Who is Portia?"),
            ("On first seeing visitors to her father's island, she exclaims, \"O brave new world, that has such people in't!\"",
             "Who is Miranda?"),
        ]),
        ("SHAKESPEARE'S VILLAINS", [
            ("After urging her husband to murder King Duncan, she sleepwalks, trying to wash away a \"damned spot\"",
             "Who is Lady Macbeth?"),
            ("This scheming ensign uses a handkerchief to convince his general that Desdemona is unfaithful",
             "Who is Iago?"),
            ("He poured poison in his sleeping brother's ear, then married the widow, Queen Gertrude",
             "Who is Claudius?"),
            ("Gloucester's illegitimate son, he plots against his half-brother Edgar in \"King Lear\"",
             "Who is Edmund?", "edmond"),
            ("This Moor, lover of the Goth queen Tamora, is the unrepentant villain of \"Titus Andronicus\"",
             "Who is Aaron?", "aaron the moor"),
        ]),
        ("NAME THE PLAY", [
            ("\"To be, or not to be: that is the question\"",
             "What is Hamlet?"),
            ("\"Friends, Romans, countrymen, lend me your ears\"",
             "What is Julius Caesar?", "caesar", "tragedy of julius caesar"),
            ("\"All the world's a stage, and all the men and women merely players\"",
             "What is As You Like It?"),
            ("\"We are such stuff as dreams are made on\"",
             "What is The Tempest?"),
            ("\"Uneasy lies the head that wears a crown\"",
             "What is Henry IV, Part 2?", "henry iv part ii", "henry iv part two", "henry iv",
             "henry 4 part 2", "henry 4", "henry the fourth part 2", "henry the fourth part two",
             "henry the fourth", "2 henry iv"),
        ]),
        ("THE BARD'S LIFE", [
            ("Shakespeare was born & buried in this Warwickshire market town",
             "What is Stratford-upon-Avon?", "stratford", "stratford on avon"),
            ("In 1582, at 18, Shakespeare married this woman, who shares her name with a modern Oscar-winning actress",
             "Who is Anne Hathaway?", "hathaway", "ann hathaway", "agnes hathaway"),
            ("Built in 1599 on London's South Bank, this open-air theater was partly owned by Shakespeare",
             "What is the Globe?", "globe theatre", "globe theater"),
            ("Shakespeare's company, the Lord Chamberlain's Men, took this new name when James I became its patron in 1603",
             "Who are the King's Men?"),
            ("Published in 1623, this collection preserved 36 of his plays, half of them never before printed",
             "What is the First Folio?", "1st folio", "folio"),
        ]),
        ("SHAKESPEAREAN SETTINGS", [
            ("\"Romeo and Juliet\" is set mainly in this \"fair\" Italian city",
             "What is Verona?"),
            ("Elsinore, the castle setting of \"Hamlet\", is in this country",
             "What is Denmark?"),
            ("\"Othello\" opens in this Italian city before the action moves to Cyprus",
             "What is Venice?"),
            ("\"Measure for Measure\" is set in this city, now the capital of Austria",
             "What is Vienna?"),
            ("In \"Macbeth\", the witches' prophecy is fulfilled when Birnam Wood appears to advance on this hill",
             "What is Dunsinane?", "dunsinane hill"),
        ]),
        ("THE BARD ON SCREEN", [
            ("This musical, filmed in 1961 & again in 2021, moves \"Romeo and Juliet\" to the streets of New York",
             "What is West Side Story?"),
            ("Heath Ledger & Julia Stiles starred in this 1999 teen comedy based on \"The Taming of the Shrew\"",
             "What is 10 Things I Hate About You?", "ten things i hate about you"),
            ("This 1998 Best Picture winner imagines young Will falling in love while writing \"Romeo and Juliet\"",
             "What is Shakespeare in Love?"),
            ("He directed & starred in 1989's \"Henry V\" & a 4-hour \"Hamlet\" in 1996",
             "Who is Kenneth Branagh?", "branagh"),
            ("Jessie Buckley won the 2026 Best Actress Oscar as Shakespeare's wife, Agnes, in this Chloe Zhao film of a Maggie O'Farrell novel",
             "What is Hamnet?"),
        ]),
        ("SONNETS & POEMS", [
            ("A Shakespearean sonnet has this many lines",
             "What is 14?", "fourteen"),
            ("Sonnet 18 opens by asking, \"Shall I compare thee to\" one of these",
             "What is a summer's day?", "summer day"),
            ("Shakespeare's sonnets are written in this meter of 5 two-syllable feet per line",
             "What is iambic pentameter?"),
            ("Many of the later sonnets are addressed to this mysterious, unnamed woman",
             "Who is the Dark Lady?", "dark lady of the sonnets"),
            ("Shakespeare's first published work was this 1593 narrative poem about a goddess & the handsome hunter she pursues",
             "What is Venus and Adonis?"),
        ]),
        ("EXIT, STAGE LEFT", [
            ("Shakespeare's Cleopatra dies from the bite of this snake, smuggled to her in a basket of figs",
             "What is an asp?"),
            ("In \"The Winter's Tale\", a famous stage direction reads \"Exit, pursued by\" this animal",
             "What is a bear?"),
            ("Macbeth is slain by this thane, who was \"from his mother's womb untimely ripp'd\"",
             "Who is Macduff?"),
            ("In the final duel, Hamlet is fatally scratched by a poisoned blade wielded by this son of Polonius",
             "Who is Laertes?"),
            ("In \"Richard III\", the Duke of Clarence is stabbed, then drowned in a butt of this sweet wine",
             "What is malmsey?", "malmsey wine"),
        ]),
        ("FINISH THE TITLE", [
            ("\"Love's Labour's ___\", in which 4 young men swear off women to study",
             "What is Lost?"),
            ("\"All's Well That ___\"",
             "What is Ends Well?"),
            ("\"The Merry Wives of ___\", a comedy set in an English town on the Thames",
             "What is Windsor?"),
            ("\"Troilus and ___\", set during the Trojan War",
             "What is Cressida?"),
            ("\"Pericles, Prince of ___\"",
             "What is Tyre?"),
        ]),
    ],

    # ========================================================== POP CULTURE
    "popculture": [
        ("CLASSIC SITCOMS", [
            ("Six twentysomething pals hang out at the Central Perk coffeehouse in this NBC sitcom",
             "What is Friends?"),
            ("Famously described as \"a show about nothing\", it starred a stand-up comic as a version of himself",
             "What is Seinfeld?"),
            ("Sam Malone tends bar & Norm has his own stool in this sitcom set in a Boston tavern",
             "What is Cheers?"),
            ("Steve Carell played Michael Scott, manager of the Scranton branch of Dunder Mifflin, on this sitcom",
             "What is The Office?"),
            ("The 1983 finale of this Korean War sitcom remains the most-watched episode of a scripted series in U.S. history",
             "What is M*A*S*H?", "mash"),
        ]),
        ("TV DRAMAS", [
            ("The Starks, Lannisters & Targaryens battle for the Iron Throne in this HBO fantasy epic",
             "What is Game of Thrones?", "got"),
            ("High school chemistry teacher Walter White becomes a drug kingpin in this AMC series",
             "What is Breaking Bad?"),
            ("James Gandolfini played a New Jersey mob boss who sees a psychiatrist in this HBO series",
             "What is The Sopranos?"),
            ("The Roy family feuds over control of the media giant Waystar Royco in this HBO drama",
             "What is Succession?"),
            ("Over 5 seasons, this HBO drama examined Baltimore through its drug trade, docks, city hall, schools & newspaper",
             "What is The Wire?"),
        ]),
        ("BLOCKBUSTERS", [
            ("Luke Skywalker, Princess Leia & Darth Vader debuted in this 1977 space epic",
             "What is Star Wars?", "star wars a new hope", "a new hope", "star wars episode iv",
             "star wars episode iv a new hope"),
            ("James Cameron's 1997 epic about a doomed ocean liner won 11 Oscars",
             "What is Titanic?"),
            ("A great white shark terrorizes Amity Island in this 1975 thriller, often called the first summer blockbuster",
             "What is Jaws?"),
            ("In July 2023 the same-day release of \"Oppenheimer\" & this film about a Mattel doll was dubbed \"Barbenheimer\"",
             "What is Barbie?"),
            ("This 2019 Marvel film capped the \"Infinity Saga\" & grossed nearly $2.8 billion worldwide",
             "What is Avengers: Endgame?", "endgame"),
        ]),
        ("BEST PICTURE WINNERS", [
            ("Marlon Brando played Vito Corleone in this 1972 crime saga",
             "What is The Godfather?"),
            ("In 2020 this South Korean thriller became the first film not in English to win Best Picture",
             "What is Parasite?", "gisaengchung"),
            ("Paul Thomas Anderson won his first Oscars when this film of his starring Leonardo DiCaprio took Best Picture in 2026",
             "What is One Battle After Another?"),
            ("Sean Baker's comedy-drama about a Brooklyn dancer who marries a Russian oligarch's son took the top prize in 2025",
             "What is Anora?"),
            ("This silent film about World War I fighter pilots won the very first Best Picture award",
             "What is Wings?"),
        ]),
        ("ANIMATION", [
            ("Woody & Buzz Lightyear star in this 1995 Pixar film, the first feature made entirely with computer animation",
             "What is Toy Story?"),
            ("Elsa & Anna are royal sisters of Arendelle in this 2013 Disney hit",
             "What is Frozen?"),
            ("In 2025 this animated musical about a K-pop girl group battling demons became Netflix's most-watched film ever",
             "What is KPop Demon Hunters?", "k pop demon hunters"),
            ("Released in 1937, it was Walt Disney's first full-length animated feature",
             "What is Snow White and the Seven Dwarfs?", "snow white", "snow white and the 7 dwarfs"),
            ("In this 2001 Hayao Miyazaki film, young Chihiro goes to work in a bathhouse for spirits",
             "What is Spirited Away?", "sen to chihiro no kamikakushi"),
        ]),
        ("SUPERHEROES", [
            ("Billionaire Bruce Wayne fights crime in Gotham City as this hero",
             "Who is Batman?", "the dark knight", "caped crusader"),
            ("Peter Parker gained his powers from the bite of a radioactive one of these",
             "What is a spider?"),
            ("Chadwick Boseman played T'Challa, king of Wakanda, in this 2018 Marvel film",
             "What is Black Panther?"),
            ("He played the Man of Steel in James Gunn's 2025 film \"Superman\"",
             "Who is David Corenswet?", "corenswet"),
            ("Wonder Woman hails from this hidden island of the Amazons",
             "What is Themyscira?", "paradise island"),
        ]),
        ("VIDEO GAMES", [
            ("This mustachioed plumber is Nintendo's mascot",
             "Who is Mario?", "super mario"),
            ("Alexey Pajitnov created this falling-blocks puzzle game in the Soviet Union in 1984",
             "What is Tetris?"),
            ("Created by Markus \"Notch\" Persson, this block-building game is the bestselling video game of all time",
             "What is Minecraft?"),
            ("The hero Link battles Ganon in this Nintendo series named for a princess",
             "What is The Legend of Zelda?", "zelda"),
            ("In 1972 this simple table-tennis game became Atari's first hit",
             "What is Pong?"),
        ]),
        ("PAGE TO SCREEN", [
            ("Daniel Radcliffe played this boy wizard created by J.K. Rowling in 8 films",
             "Who is Harry Potter?"),
            ("Katniss Everdeen volunteers as tribute in this dystopian series by Suzanne Collins",
             "What is The Hunger Games?"),
            ("Peter Jackson filmed this J.R.R. Tolkien trilogy in his native New Zealand",
             "What is The Lord of the Rings?", "lotr"),
            ("Denis Villeneuve directed the recent film adaptations of this Frank Herbert novel set on the desert planet Arrakis",
             "What is Dune?"),
            ("Margaret Atwood's novel about the theocracy of Gilead became this Hulu series in 2017",
             "What is The Handmaid's Tale?"),
        ]),
        ("GAME & REALITY SHOWS", [
            ("Since 2000, Jeff Probst has snuffed torches at Tribal Council on this CBS reality show",
             "What is Survivor?"),
            ("Ryan Seacrest took over as host of this game show in 2024 after Pat Sajak's 41 seasons",
             "What is Wheel of Fortune?", "wheel"),
            ("\"Come on down!\" is the signature call of this game show hosted by Bob Barker & then Drew Carey",
             "What is The Price Is Right?"),
            ("Kelly Clarkson won the first season of this singing competition in 2002",
             "What is American Idol?", "idol"),
            ("On this British competition, a handshake from judge Paul Hollywood is the ultimate praise",
             "What is The Great British Bake Off?", "great british baking show", "bake off", "gbbo"),
        ]),
        ("NAME THE MOVIE", [
            ("\"There's no place like home\"",
             "What is The Wizard of Oz?"),
            ("\"I'll be back\" (1984)",
             "What is The Terminator?"),
            ("\"Here's looking at you, kid\"",
             "What is Casablanca?"),
            ("\"You can't handle the truth!\"",
             "What is A Few Good Men?"),
            ("\"I coulda been a contender\"",
             "What is On the Waterfront?"),
        ]),
        ("STREAMING HITS", [
            ("Kids in Hawkins, Indiana battle monsters from the Upside Down in this Netflix series",
             "What is Stranger Things?"),
            ("Cash-strapped contestants play deadly versions of children's games in this South Korean Netflix series",
             "What is Squid Game?", "squid games"),
            ("Pedro Pascal plays a helmeted bounty hunter who protects little Grogu in this \"Star Wars\" series",
             "What is The Mandalorian?", "mando"),
            ("Jeremy Allen White plays chef Carmy Berzatto, who takes over his family's Chicago sandwich shop, in this series",
             "What is The Bear?"),
            ("Adam Scott plays an office worker whose job & home memories have been surgically split in this Apple TV series",
             "What is Severance?"),
        ]),
        ("DIRECTORS", [
            ("\"E.T.\", \"Jurassic Park\" & \"Schindler's List\"",
             "Who is Steven Spielberg?", "spielberg"),
            ("\"Psycho\", \"Vertigo\" & \"The Birds\"",
             "Who is Alfred Hitchcock?", "hitchcock"),
            ("\"Pulp Fiction\", \"Kill Bill\" & \"Django Unchained\"",
             "Who is Quentin Tarantino?", "tarantino"),
            ("This \"Frances Ha\" co-writer directed \"Lady Bird\" & 2019's \"Little Women\"",
             "Who is Greta Gerwig?", "gerwig"),
            ("In 2010 she became the first woman to win the Best Director Oscar, for \"The Hurt Locker\"",
             "Who is Kathryn Bigelow?", "bigelow"),
        ]),
    ],

    # ================================================================ MUSIC
    "music": [
        ("CLASSICAL COMPOSERS", [
            ("Though he went deaf, he composed 9 symphonies, the last featuring the \"Ode to Joy\"",
             "Who is Ludwig van Beethoven?", "beethoven"),
            ("This Salzburg-born prodigy composed \"The Magic Flute\" & \"Eine kleine Nachtmusik\"",
             "Who is Wolfgang Amadeus Mozart?", "mozart", "wolfgang mozart"),
            ("This German Baroque master wrote the \"Brandenburg Concertos\" & \"The Well-Tempered Clavier\"",
             "Who is Johann Sebastian Bach?", "bach", "j s bach"),
            ("Nicknamed the \"Red Priest\" for his hair, this Venetian composed \"The Four Seasons\"",
             "Who is Antonio Vivaldi?", "vivaldi"),
            ("This Czech composer wrote his \"New World\" Symphony in 1893 while living in the United States",
             "Who is Antonin Dvorak?", "dvorak"),
        ]),
        ("THE BEATLES", [
            ("The Beatles got their start in this English port city",
             "What is Liverpool?"),
            ("Born Richard Starkey, he was the band's drummer",
             "Who is Ringo Starr?", "ringo"),
            ("Dozens of famous faces crowd the collage on the cover of this landmark 1967 album",
             "What is Sgt. Pepper's Lonely Hearts Club Band?", "sgt pepper", "sgt peppers",
             "sergeant peppers lonely hearts club band", "sergeant pepper", "sergeant peppers"),
            ("The cover of this 1969 album, the last the band recorded, shows the 4 crossing a London street",
             "What is Abbey Road?"),
            ("He managed the Beatles from the early 1960s until his death in 1967",
             "Who is Brian Epstein?", "epstein"),
        ]),
        ("ROCK & ROLL", [
            ("Born in Tupelo, Mississippi, this \"King of Rock and Roll\" made his home at Graceland",
             "Who is Elvis Presley?", "elvis", "presley"),
            ("Freddie Mercury was the flamboyant frontman of this British band",
             "What is Queen?"),
            ("Kurt Cobain fronted this grunge band whose 1991 album \"Nevermind\" topped the charts",
             "What is Nirvana?"),
            ("This band's 1973 album \"The Dark Side of the Moon\" has spent more than 900 weeks on the Billboard 200",
             "What is Pink Floyd?"),
            ("This guitarist's searing take on the national anthem was a highlight of his festival-closing set at Woodstock in 1969",
             "Who is Jimi Hendrix?", "hendrix"),
        ]),
        ("POP STARS", [
            ("Her Eras Tour of 2023-24 was the first concert tour to gross more than $2 billion",
             "Who is Taylor Swift?", "swift"),
            ("She won her first Album of the Year Grammy in 2025 for \"Cowboy Carter\"",
             "Who is Beyonce?", "beyonce knowles", "beyonce knowles carter"),
            ("This Puerto Rican superstar headlined the Super Bowl LX halftime show in February 2026",
             "Who is Bad Bunny?", "benito", "benito antonio martinez ocasio"),
            ("At the 2020 Grammys, this 18-year-old swept all 4 major categories, including Album of the Year",
             "Who is Billie Eilish?", "eilish"),
            ("This Missouri-born \"Pink Pony Club\" singer was named Best New Artist at the 2025 Grammys",
             "Who is Chappell Roan?", "roan"),
        ]),
        ("HIP-HOP & R&B", [
            ("Marshall Mathers is the real name of this Detroit rapper, a.k.a. Slim Shady",
             "Who is Eminem?"),
            ("Known as the \"Queen of Soul\", she had her signature hit with 1967's \"Respect\"",
             "Who is Aretha Franklin?", "aretha"),
            ("In 2018 this Compton rapper won the Pulitzer Prize for Music for his album \"DAMN.\"",
             "Who is Kendrick Lamar?", "kendrick", "lamar"),
            ("Born Shawn Carter in Brooklyn, this rapper & mogul married Beyonce in 2008",
             "Who is Jay-Z?", "hov"),
            ("This 1979 Sugarhill Gang single became the first rap record to reach the Top 40",
             "What is Rapper's Delight?"),
        ]),
        ("COUNTRY MUSIC", [
            ("This \"Jolene\" & \"9 to 5\" singer has her own Tennessee theme park",
             "Who is Dolly Parton?", "dolly", "parton"),
            ("\"The Man in Black\", he recorded a famous live album at Folsom Prison in 1968",
             "Who is Johnny Cash?", "cash"),
            ("On the air since 1925, this Nashville radio show is country music's most famous stage",
             "What is the Grand Ole Opry?", "opry", "grand old opry"),
            ("This Texan outlaw-country legend recorded \"Red Headed Stranger\"; his battered guitar is named Trigger",
             "Who is Willie Nelson?", "willie", "nelson"),
            ("Known for \"Crazy\" & \"Walkin' After Midnight\", she died in a 1963 plane crash at age 30",
             "Who is Patsy Cline?", "cline"),
        ]),
        ("MUSICAL INSTRUMENTS", [
            ("A standard modern one of these has 88 keys",
             "What is a piano?", "pianoforte"),
            ("A standard guitar has this many strings",
             "What is 6?", "six"),
            ("Instead of valves, this brass instrument changes pitch with a slide",
             "What is a trombone?", "slide trombone"),
            ("The orchestra traditionally tunes to an A sounded by this double-reed woodwind",
             "What is an oboe?"),
            ("Invented by a Russian physicist around 1920, this eerie-sounding electronic instrument is played without being touched",
             "What is a theremin?"),
        ]),
        ("BROADWAY MUSICALS", [
            ("Lin-Manuel Miranda blended hip-hop & history in this musical about the first Treasury secretary",
             "What is Hamilton?"),
            ("Elphaba & Glinda are the witches of Oz in this musical that opened on Broadway in 2003",
             "What is Wicked?"),
            ("Andrew Lloyd Webber's musical about a masked figure haunting the Paris Opera, it ran a record 35 years on Broadway",
             "What is The Phantom of the Opera?", "phantom"),
            ("Based on a Victor Hugo novel, this musical follows ex-convict Jean Valjean",
             "What is Les Miserables?", "les mis", "les miz"),
            ("This composer-lyricist wrote \"Sweeney Todd\", \"Company\" & \"Into the Woods\"",
             "Who is Stephen Sondheim?", "sondheim"),
        ]),
        ("OPERA", [
            ("From Italian for \"first lady\", it's the term for the leading female singer in an opera company",
             "What is a prima donna?", "primadonna"),
            ("Georges Bizet composed this opera about a fiery worker in a Seville cigarette factory",
             "What is Carmen?"),
            ("In this Puccini opera, the young geisha Cio-Cio-San is abandoned by Lieutenant Pinkerton",
             "What is Madama Butterfly?", "madame butterfly", "butterfly"),
            ("He composed \"Rigoletto\", \"La Traviata\" & \"Aida\"",
             "Who is Giuseppe Verdi?", "verdi"),
            ("\"Das Rheingold\" & \"Die Walkure\" are the first 2 of the 4 operas in this Wagner cycle",
             "What is the Ring cycle?", "ring", "der ring des nibelungen", "ring of the nibelung"),
        ]),
        ("MUSICAL TERMS", [
            ("It's the highest of the standard female singing voices",
             "What is soprano?", "a soprano"),
            ("In sheet music, a letter \"f\" stands for this Italian word meaning \"loud\"",
             "What is forte?"),
            ("From Italian for \"growing\", it's a gradual increase in loudness",
             "What is a crescendo?"),
            ("From Italian for \"in the chapel style\", it means singing without instrumental accompaniment",
             "What is a cappella?", "acapella", "a capella", "acappella"),
            ("It's the technique of plucking, rather than bowing, the strings of an instrument like the violin",
             "What is pizzicato?"),
        ]),
        ("JAZZ & BLUES", [
            ("Nicknamed Satchmo, this New Orleans-born trumpeter sang \"What a Wonderful World\"",
             "Who is Louis Armstrong?", "armstrong"),
            ("Called the \"First Lady of Song\", she was famed for her scat singing",
             "Who is Ella Fitzgerald?", "ella", "fitzgerald"),
            ("This trumpeter's 1959 album \"Kind of Blue\" is often cited as the bestselling jazz record ever",
             "Who is Miles Davis?", "miles", "davis"),
            ("This \"King of the Blues\" named his guitars Lucille",
             "Who is B.B. King?", "riley b king"),
            ("This saxophonist recorded the spiritual 4-part suite \"A Love Supreme\" in 1964",
             "Who is John Coltrane?", "coltrane", "trane"),
        ]),
        ("LANDMARK ALBUMS", [
            ("\"Billie Jean\" & \"Beat It\" are on this 1982 Michael Jackson album, the bestselling of all time",
             "What is Thriller?"),
            ("Fleetwood Mac recorded this 1977 blockbuster while its members' romances were falling apart",
             "What is Rumours?", "rumors"),
            ("Albums by this British singer include \"19\", \"21\", \"25\" & \"30\"",
             "Who is Adele?"),
            ("Prince starred in the 1984 film that shares its title with this album of his",
             "What is Purple Rain?"),
            ("This 1971 Carole King album spent 15 weeks at No. 1 & won the Grammy for Album of the Year",
             "What is Tapestry?"),
        ]),
    ],
}

# Final Jeopardy! clues: (category, clue text, correct response, *other accepted)
FINALS = {
    "africa": [
        ("AFRICAN COUNTRIES",
         "It's the only independent country in Africa where Spanish is an official language",
         "What is Equatorial Guinea?"),
        ("COUNTRY NAMES",
         "A 15th-century Portuguese explorer gave this West African country its name, meaning \"lion mountains\"",
         "What is Sierra Leone?"),
        ("AFRICAN CAPITALS",
         "Founded in the 1880s by the future Emperor Menelik II, this capital has a name meaning "
         "\"new flower\" in Amharic",
         "What is Addis Ababa?"),
    ],
    "water": [
        ("WORLD RIVERS",
         "It's the only major river in the world that crosses the Equator twice",
         "What is the Congo?", "congo river", "zaire river"),
        ("GEOGRAPHIC NAMES",
         "Named for a 16th-century English sea captain, this passage separates South America's Cape Horn from Antarctica",
         "What is the Drake Passage?", "drake", "drakes passage"),
        ("LAKES",
         "Measured by surface area, it's the largest lake in the world that lies entirely within one country",
         "What is Lake Michigan?", "michigan"),
    ],
    "presidents": [
        ("U.S. PRESIDENTS",
         "He's the only U.S. president who never married",
         "Who is James Buchanan?", "buchanan"),
        ("PRESIDENTIAL EDUCATION",
         "With a doctorate from Johns Hopkins, he's the only U.S. president to have earned a Ph.D.",
         "Who is Woodrow Wilson?", "wilson"),
        ("PRESIDENTIAL BIRTHPLACES",
         "Eight presidents, more than from any other state, were born in this state",
         "What is Virginia?"),
    ],
    "shakespeare": [
        ("SHAKESPEARE & THE CALENDAR",
         "Shakespeare died on April 23, 1616, the feast day of this patron saint of England",
         "Who is St. George?", "saint george", "george"),
        ("ASTRONOMY & LITERATURE",
         "Titania, Oberon & Puck are among the moons of this planet, most of which are named for Shakespeare characters",
         "What is Uranus?"),
        ("SHAKESPEARE'S PLAYS",
         "With some 4,000 lines, it's the longest of Shakespeare's plays",
         "What is Hamlet?"),
    ],
    "popculture": [
        ("TELEVISION HISTORY",
         "Debuting in December 1989, it's the longest-running scripted primetime series in American TV history",
         "What is The Simpsons?"),
        ("MOVIE CHARACTERS",
         "Between 1962 & 2021, six different actors played this character in 25 films from Eon Productions",
         "Who is James Bond?", "bond", "007", "agent 007"),
        ("THE OSCARS",
         "The third film to win 11 Academy Awards, it's the only one of them to win in every category in which it was nominated",
         "What is The Lord of the Rings: The Return of the King?", "return of the king",
         "lotr return of the king"),
    ],
    "music": [
        ("NOBEL LAUREATES",
         "In 2016 this singer-songwriter won the Nobel Prize in Literature for \"new poetic "
         "expressions within the great American song tradition\"",
         "Who is Bob Dylan?", "dylan", "robert zimmerman"),
        ("MUSICAL INSTRUMENTS",
         "Patented in Paris in 1846, this instrument is named for its Belgian inventor, Adolphe",
         "What is the saxophone?", "sax"),
        ("PATRIOTIC SONGS",
         "The words of \"The Star-Spangled Banner\" were inspired by the 1814 British bombardment of this Baltimore fort",
         "What is Fort McHenry?", "mchenry", "ft mchenry"),
    ],
}


# --------------------------------------------------------------------------
#  ANSWER CHECKING
# --------------------------------------------------------------------------
QUESTION_RE = re.compile(r"^\s*(who|what|where|when|why|how)\b", re.I)
LEAD_WORDS = {"what", "who", "where", "when", "whats", "whos", "wheres"}
LEAD_VERBS = {"is", "are", "was", "were"}
ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19,
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
        "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90}
ROMAN = {"ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9,
         "x": 10, "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16}
EXACT_ONLY = {"hamlet", "hamnet"}          # near-twins that must never fuzzy-match
ABBREVIATIONS = {"mt": "mount", "st": "saint", "ft": "fort"}
# A type word that may be left off: "Lake Victoria" -> "Victoria", "Nile River" -> "Nile".
LEAD_TYPE = {"lake", "mount", "river", "loch", "saint"}
TRAIL_TYPE = {"river", "lake", "sea", "ocean", "falls", "desert", "mountains", "mountain",
              "canal", "island", "islands", "city", "peninsula", "trench", "theatre",
              "theater", "cycle"}
# Given names: "Kenneth Branagh" may be answered "Branagh".
FIRST_NAMES = set("""
aaron abigail abraham adam adele al alan albert alec alex alexander alfred alice amelia
amy andrew andy angela anne anna anthony antonio aretha ariana arnold arthur audrey barack
barbara barry ben benjamin benedict bernard beth betty beyonce bill billie billy bob bobby
brad brian bruce calvin carl carlos carol carrie catherine charles charlie chester chris
christopher cindy claude clint dan daniel danny dave david denzel diana diane dolly donald
doris dorothy douglas dwight eddie edgar edith edward elizabeth ella ellen elton elvis
emily emma eric ernest ethel eugene eva fidel florence frances francis frank franklin
fred frederick gary gene geoffrey george gerald gertrude gloria gordon greg gregory greta
grover gustav hank harold harriet harry helen henry herbert herman hillary howard hugh
ian ingrid isaac jack jackie jacqueline james jane janet jason jay jean jeff jennifer
jeremy jerry jesse jessica jessie jim jimi jimmy joan joe joel johann john johnny jon
jonathan joseph josh joyce judy julia julie julius justin kamala karl kate katharine
katherine kathryn keith kelly ken kendrick kenneth kevin kurt larry laura lauren laurence
lawrence leo leon leonard leonardo lewis linda lionel lisa louis louisa lucille ludwig
luke lyndon madonna marc marcel margaret maria marie marilyn mario marlon martha martin
marvin mary matt matthew maya meryl michael michelle mick mike miles millard nancy
napoleon natalie nathaniel neil nelson nicholas nick nicole nikola noah norman oliver
oprah orson oscar pablo pat patricia patrick patsy paul peter phil philip pierre quentin
rachel ralph ray rebecca richard rick ringo robert robin rod roger ron ronald rosa
rudyard russell ruth rutherford ryan sally sam samuel sandra sarah scott sean serena
sigmund simon sofia spiro stan stanley stephen steve steven stevie susan sylvia taylor
ted teddy theodore thomas tim timothy tina toni tom tommy tony truman ulysses vincent
vladimir walt walter warren wayne whitney will willa william willie winston wolfgang
woodrow zachary zora
""".split())
AMBIGUOUS_SURNAMES = {"adams", "roosevelt", "bush", "johnson", "harrison", "bronte"}
NOT_A_SURNAME = {"jr", "sr", "show", "day", "award", "prize", "bowl", "cup", "act"}


def _tokens(text):
    """Lower-case words with accents and punctuation removed; 'the' dropped."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"['\u2019`]", "", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    words = [ABBREVIATIONS.get(w, w) for w in text.split() if w != "the"]
    if len(words) > 1 and words[0] in ("a", "an"):
        words = words[1:]
    return words


def _numeric(words):
    """'henry the fifth' / 'henry v' / 'henry 5th' -> 'henry 5'."""
    out, i = [], 0
    while i < len(words):
        word = words[i]
        ordinal = re.match(r"^(\d+)(st|nd|rd|th)$", word)
        if word in TENS and i + 1 < len(words) and 0 < ONES.get(words[i + 1], 0) < 10:
            out.append(str(TENS[word] + ONES[words[i + 1]]))
            i += 2
            continue
        if word in ONES:
            out.append(str(ONES[word]))
        elif word in TENS:
            out.append(str(TENS[word]))
        elif word in ROMAN:
            out.append(str(ROMAN[word]))
        elif ordinal:
            out.append(ordinal.group(1))
        else:
            out.append(word)
        i += 1
    return out


def normalize(text):
    return " ".join(_tokens(text))


def _forms(words):
    """A word list as plain text and with numbers unified."""
    out = [" ".join(words)]
    numeric = " ".join(_numeric(words))
    if numeric != out[0]:
        out.append(numeric)
    return out


def given_forms(text):
    """Ways to read what the player typed (with and without 'What is')."""
    words = _tokens(text)
    out = _forms(words)
    if len(words) > 1 and words[0] in LEAD_WORDS:
        rest = words[1:]
        if len(rest) > 1 and rest[0] in LEAD_VERBS:
            rest = rest[1:]
        if len(rest) > 1 and rest[0] in ("a", "an"):
            rest = rest[1:]
        out += _forms(rest)
    return [f for f in out if f]


def target_forms(answers):
    """(full, short): full answers, and shortened ones accepted only on an exact match."""
    full, short = [], []
    for answer in answers:
        words = _tokens(answer)
        if not words:
            continue
        full += _forms(words)
        trimmed = list(words)
        if len(trimmed) > 1 and "of" not in trimmed:
            if trimmed[0] in LEAD_TYPE:
                trimmed = trimmed[1:]
            elif trimmed[-1] in TRAIL_TYPE:
                trimmed = trimmed[:-1]
        if trimmed != words and len(" ".join(trimmed)) >= 4:
            short += _forms(trimmed)
        is_person = (2 <= len(words) <= 4 and not {"of", "and", "in", "on"} & set(words)
                     and (words[0] in FIRST_NAMES or len(words[0]) == 1))
        if is_person:
            surname = words[-1]
            if (len(surname) >= 3 and surname not in AMBIGUOUS_SURNAMES
                    and surname not in NOT_A_SURNAME and not surname.isdigit()):
                short.append(surname)
                no_initials = [w for w in words[1:-1] if len(w) > 1]
                short.append(" ".join([words[0]] + no_initials + [surname]))
    return full, short


def edit_distance(a, b):
    """Optimal string alignment distance (a swap of neighbours counts as 1)."""
    rows = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        rows[i][0] = i
    for j in range(len(b) + 1):
        rows[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[-1][-1]


def _strict_tokens(text):
    """Short words, initials and numbers must match exactly (W. vs H.W., 4 vs 5)."""
    return sorted(t for t in text.split() if len(t) <= 3 or t.isdigit())


def close_enough(given, target):
    if given == target or given.replace(" ", "") == target.replace(" ", ""):
        return True
    if given in EXACT_ONLY or target in EXACT_ONLY:
        return False
    if len(target) < 5 or given[0] != target[0]:
        return False
    if _strict_tokens(given) != _strict_tokens(target):
        return False
    return edit_distance(given, target) <= (1 if len(target) <= 9 else 2)


def _contains(given, target):
    """The full answer appears inside a slightly longer response ('President Lincoln')."""
    if len(target) < 4:
        return False
    g, t = given.split(), target.split()
    if not len(t) < len(g) <= len(t) + 3:
        return False
    return any(g[i:i + len(t)] == t for i in range(len(g) - len(t) + 1))


def is_correct(given, accepted):
    """True if the typed response matches an accepted answer (typo tolerant)."""
    candidates = given_forms(given)
    if not candidates:
        return False
    full, short = target_forms(accepted)
    for cand in candidates:
        if any(close_enough(cand, target) or _contains(cand, target) for target in full):
            return True
        if any(close_enough(cand, target) for target in short):
            return True
    return False


# --------------------------------------------------------------------------
#  CLUE POOL: built-in practice set
# --------------------------------------------------------------------------
def bare_answer(display):
    """'What is the Nile?' -> 'the Nile'."""
    return re.sub(r"^(What|Who|Where) (is|are|was|were) ", "", display).rstrip("?")


def builtin_pool():
    cats, finals = [], []
    for theme, entries in BANK.items():
        for name, clues in entries:
            cats.append({"name": name, "themes": {theme}, "air": None, "round": None,
                         "comment": "", "source": "practice", "key": "practice|" + name,
                         "clues": [(c[0], c[1], [bare_answer(c[1])] + list(c[2:]))
                                   for c in clues]})
    for theme, entries in FINALS.items():
        for number, f in enumerate(entries):
            finals.append({"name": f[0], "themes": {theme}, "air": None, "source": "practice",
                           "key": "practice|F|%s|%d" % (theme, number),
                           "clue": (f[1], f[2], [bare_answer(f[2])] + list(f[3:]))})
    return cats, finals


# --------------------------------------------------------------------------
#  CLUE POOL: clue files (show archive or your own)
# --------------------------------------------------------------------------
def name_themes(name):
    """Themes a category name is a candidate for."""
    return {key for key, info in THEMES.items()
            if info["name"].search(name) and not info["skip"].search(name)}


def confirm_themes(candidates, clues):
    """Keep a theme only if enough of the clues are really about it."""
    kept = set()
    for key in candidates:
        info = THEMES[key]
        if info["content"] is None:
            kept.add(key)
            continue
        hits = sum(1 for clue in clues if info["content"].search(clue[0] + " " + clue[1]))
        if hits >= info["need"]:
            kept.add(key)
    return kept


YEAR_AGO = "%04d%s" % (date.today().year - 1, date.today().isoformat()[4:])


def accepted_answers(clue):
    """Accepted answers for a clue (worked out on demand for clue-file clues)."""
    return clue[2] if clue[2] is not None else answer_variants(clue[1])


def is_dated(text, response="", air=""):
    """True if a clue's wording or subject may have gone out of date since it aired."""
    low = text.lower()
    if any(hint in low for hint in STALE_HINTS) and STALE_RE.search(text):
        return True
    if not air:
        return False
    if air < YEAR_AGO and any(hint in low for hint in VOLATILE_HINTS) and VOLATILE_RE.search(text):
        return True
    both = text + " " + response
    low = both.lower()
    if not any(hint in low for hint in CHANGE_HINTS):
        return False
    return any(air < day and pattern.search(both) for day, pattern in WORLD_CHANGES)


def needs_media(text):
    low = text.lower()
    return any(hint in low for hint in MEDIA_HINTS) and bool(MEDIA_RE.search(text))


def answer_variants(response):
    """'(Jeremy) Irons' -> Irons / Jeremy Irons;  'Augustus (Octavian)' -> + Octavian."""
    without = re.sub(r"\([^)]*\)", " ", response)
    out = [without, response.replace("(", " ").replace(")", " ")]
    tail = re.search(r"\(([^)]*)\)\s*$", response)
    if tail and normalize(without):
        inner = re.sub(r"^(or|aka|a\.k\.a\.|also|i\.e\.)\s+", "", tail.group(1).strip(), flags=re.I)
        if len(inner) >= 4 and not re.match(r"(from|in|of|as|for|with|to|on|at|by|not)\b", inner, re.I):
            out.append(inner)
    return [v for v in out if normalize(v)] or [response]


def _clean(value):
    value = "" if value is None else str(value)
    if "&" in value:
        value = html.unescape(value)
    if "<" in value:
        value = TAG_RE.sub("", value)
    if "\\" in value:
        value = value.replace('\\"', '"').replace("\\'", "'")
    return " ".join(value.split())


def _read_table(path):
    """Returns (column names, rows as lists)."""
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        if path.lower().endswith(".json"):
            raw = json.load(fh)
            if isinstance(raw, dict):
                raw = raw.get("clues") or raw.get("data") or []
            raw = [r for r in raw if isinstance(r, dict)]
            header = []
            for r in raw[:200]:
                header += [k for k in r if k not in header]
            return header, [[r.get(k) for k in header] for r in raw]
        head = fh.readline()
        fh.seek(0)
        if head.count("\t") >= head.count(","):
            rows = list(csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))
        else:
            rows = list(csv.reader(fh))
    return (rows[0], rows[1:]) if rows else ([], [])


def load_clue_file(path, since=None, stats=None):
    """Read one TSV/CSV/JSON clue file. Returns (categories, finals)."""
    stats = stats if stats is not None else {}
    header, rows = _read_table(path)
    header = [str(h or "").strip().lower().replace(" ", "_") for h in header]
    if not rows:
        raise ValueError("no clue rows found")

    def col(*names):
        return next((header.index(n) for n in names if n in header), None)

    def cell(row, index):
        if index is None or index >= len(row) or row[index] is None:
            return ""
        return str(row[index])

    i_cat = col("category")
    i_clue, i_resp = col("clue", "clue_text"), col("response", "correct_response")
    if (i_clue is None or i_resp is None) and "answer" in header and "question" in header:
        # The show archive calls the clue "answer" and the response "question";
        # some other exports do the opposite. The longer column is the clue.
        i_a, i_q = header.index("answer"), header.index("question")
        len_a = sum(len(cell(r, i_a)) for r in rows[:500])
        len_q = sum(len(cell(r, i_q)) for r in rows[:500])
        i_clue, i_resp = (i_a, i_q) if len_a >= len_q else (i_q, i_a)
    if i_cat is None or i_clue is None or i_resp is None:
        raise ValueError("needs columns 'category' plus 'answer'/'question' (or 'clue'/"
                         "'response'); found: " + ", ".join(header))
    i_val, i_date = col("clue_value", "value"), col("air_date", "date")
    i_round, i_note = col("round"), col("comments", "comment")
    label = os.path.basename(path)

    groups, final_rows = {}, []
    for index, row in enumerate(rows):
        air = cell(row, i_date).strip()
        if since:
            year = re.search(r"(19|20)\d\d", air)
            if not year or int(year.group(0)) < since:
                continue
        rnd = cell(row, i_round).strip().lower()
        if rnd == "3" or "final" in rnd:
            final_rows.append((air, row))
        else:
            groups.setdefault((air, rnd, cell(row, i_cat)), []).append((index, row))

    finals = []
    for air, row in final_rows:
        name = _clean(cell(row, i_cat)).upper()
        text, resp = _clean(cell(row, i_clue)), _clean(cell(row, i_resp))
        if name and text and resp and not needs_media(text) and not is_dated(text, resp, air):
            finals.append({"name": name, "themes": name_themes(name), "air": air or None,
                           "source": "show", "key": "%s|F|%s" % (air or label, name),
                           "clue": (text, resp, None)})

    cats = []
    for (air, rnd, raw_name), items in groups.items():
        name = _clean(raw_name).upper()
        if not name:
            continue
        if len(items) < 5 or (air and len(items) != 5):
            stats["incomplete"] = stats.get("incomplete", 0) + 1
            continue
        if i_val is not None:
            items.sort(key=lambda item: (int(re.sub(r"\D", "", cell(item[1], i_val)) or 0),
                                         item[0]))
        clues, comment = [], ""
        for _index, row in items[:5]:
            text, resp = _clean(cell(row, i_clue)), _clean(cell(row, i_resp))
            if text and resp:
                clues.append((text, resp, None))
            comment = comment or _clean(cell(row, i_note))
        if len(clues) != 5:
            stats["incomplete"] = stats.get("incomplete", 0) + 1
            continue
        if UNPLAYABLE_RE.search(name) or any(needs_media(c[0]) for c in clues):
            stats["visual"] = stats.get("visual", 0) + 1
            continue
        if any(is_dated(c[0], c[1], air) for c in clues):
            stats["dated"] = stats.get("dated", 0) + 1
            continue
        candidates = name_themes(name)
        cats.append({"name": name,
                     "themes": confirm_themes(candidates, clues) if candidates else set(),
                     "air": air or None, "round": {"1": 1, "2": 2}.get(rnd),
                     "comment": comment, "source": "show", "clues": clues,
                     "key": "%s|%s|%s" % (air or label, rnd, name)})
    return cats, finals


def build_mixes(cats):
    """Extra categories for narrow seeds, assembled from single clues.

    For a theme with a "mix" rule, clues whose response matches are taken from
    other categories (keeping their row, so $200 clues stay easy) and dealt, newest
    first, into five-clue categories. Each clue remembers where it came from,
    and a mix is dated by its oldest clue.
    """
    mixes = []
    for key, info in THEMES.items():
        rule = info.get("mix")
        if not rule:
            continue
        buckets = {}
        for cat in cats:
            if key in cat["themes"] or cat["round"] not in (1, 2) or not cat["air"]:
                continue
            if not rule["host"].search(cat["name"]) or info["skip"].search(cat["name"]):
                continue
            for row, clue in enumerate(cat["clues"]):
                if rule["clue"].search(clue[1]):
                    origin = {"name": cat["name"], "air": cat["air"], "comment": cat["comment"]}
                    buckets.setdefault((cat["round"], row), []).append(
                        (cat["air"], cat["key"], (clue[0], clue[1], None, origin)))
        number = 0
        for rnd in (1, 2):
            rows = [sorted(buckets.get((rnd, row), []), key=lambda item: item[:2], reverse=True)
                    for row in range(5)]
            count = min(len(row) for row in rows)
            for j in range(count - 1, -1, -1):          # oldest first, so numbers stay put
                picked = [rows[row][j] for row in range(5)]
                ident = "|".join("%s|%d" % (item[1], row) for row, item in enumerate(picked))
                number += 1
                mixes.append({
                    "name": "%s MIX #%d" % (info["title"].upper(), number),
                    "themes": {key}, "air": min(item[0] for item in picked), "round": rnd,
                    "comment": "", "source": "show", "clues": [item[2] for item in picked],
                    "key": "mix|%s|%s" % (key, hashlib.md5(ident.encode("utf-8")).hexdigest()[:12])})
    return mixes


def clue_files(paths):
    """Expand files and folders into a list of clue files."""
    found = []
    for path in paths:
        if os.path.isdir(path):
            for ext in ("tsv", "csv", "json"):
                found += sorted(glob.glob(os.path.join(path, "*." + ext)))
        elif os.path.exists(path):
            found.append(path)
    unique = []
    for path in found:
        if os.path.abspath(path) not in [os.path.abspath(p) for p in unique]:
            unique.append(path)
    return unique


def load_show_pool(files, since=None, cache_path=None):
    """Load every clue file. The parsed result is cached so later starts are fast."""
    signature = [[os.path.abspath(p), os.path.getsize(p), int(os.path.getmtime(p))]
                 for p in [__file__] + list(files)] + [VERSION, since, YEAR_AGO[:7]]
    if cache_path:
        cached = load_json(cache_path, {})
        if cached.get("signature") == signature:
            for item in cached["cats"] + cached["finals"]:
                item["themes"] = set(item["themes"])
            return cached["cats"], cached["finals"], cached["stats"]
    if cache_path:
        print(" Reading the clue files (only needed after a download) ...")
    cats, finals, stats = {}, {}, {}
    for path in files:
        try:
            file_cats, file_finals = load_clue_file(path, since, stats)
        except (OSError, ValueError) as err:
            print(" (Skipping %s: %s)" % (path, err))
            continue
        for cat in file_cats:
            cats.setdefault(cat["key"], cat)
        for final in file_finals:
            finals.setdefault(final["key"], final)
    cats = list(cats.values())
    mixes = build_mixes(cats)
    stats["mixes"] = len(mixes)
    cats, finals = cats + mixes, list(finals.values())
    if cache_path and cats:
        try:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            with open(cache_path + ".part", "w", encoding="utf-8") as fh:
                json.dump({"signature": signature, "stats": stats,
                           "cats": [dict(c, themes=sorted(c["themes"])) for c in cats],
                           "finals": [dict(f, themes=sorted(f["themes"])) for f in finals]},
                          fh, separators=(",", ":"))
            os.replace(cache_path + ".part", cache_path)
        except OSError:
            pass                                  # the cache is only a convenience
    return cats, finals, stats


# --------------------------------------------------------------------------
#  DOWNLOADING SHOW CLUES
# --------------------------------------------------------------------------
def fetch_seasons(dest, count):
    """Download the newest `count` season files into dest. Returns True on success."""
    import urllib.error
    import urllib.request

    def get(season):
        request = urllib.request.Request(SOURCE_URL.format(n=season),
                                         headers={"User-Agent": "jtrainer/" + VERSION})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise

    def manual_help(reason):
        print(" Download failed: %s" % reason)
        print(" You can get the files by hand instead:")
        print("   1. Open %s" % SOURCE_PAGE)
        print("   2. Download the newest files from its 'seasons' folder (season%d.tsv ...)"
              % KNOWN_SEASON)
        print("   3. Put them in %s" % dest)
        return False

    def with_git():
        """Second route: a partial git clone that only downloads the wanted files."""
        git = shutil.which("git")
        if not git:
            return 0
        tmp = tempfile.mkdtemp(prefix="jtrainer-")

        def run(*git_args):
            return subprocess.run([git] + list(git_args), check=True, capture_output=True,
                                  universal_newlines=True, timeout=900).stdout

        try:
            print(" Direct download did not work - trying git instead ...")
            run("clone", "--depth", "1", "--filter=blob:none", "--no-checkout", SOURCE_PAGE, tmp)
            names = run("-C", tmp, "ls-tree", "--name-only", "HEAD", "seasons/").split()
            seasons = sorted((int(m.group(1)), name) for name in names
                             for m in [re.search(r"season(\d+)\.tsv$", name)] if m)[-count:]
            run("-C", tmp, "checkout", "HEAD", "--", *[name for _, name in seasons])
            for season, name in reversed(seasons):
                target = os.path.join(dest, "season%d.tsv" % season)
                shutil.copyfile(os.path.join(tmp, name), target)
                print("   season %d   %4.1f MB" % (season, os.path.getsize(target) / 1e6))
            return len(seasons)
        except (subprocess.SubprocessError, OSError, ValueError):
            return 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    count = max(1, count)
    print(" Looking for the newest season in the clue archive ...")
    try:
        os.makedirs(dest, exist_ok=True)
        blobs = {KNOWN_SEASON: get(KNOWN_SEASON)}
        if blobs[KNOWN_SEASON] is None:
            return manual_help("the archive has moved (season %d not found)" % KNOWN_SEASON)
        latest = KNOWN_SEASON
        for season in range(KNOWN_SEASON + 1, KNOWN_SEASON + 15):
            data = get(season)
            if data is None:
                break
            blobs[season], latest = data, season
        saved = 0
        for season in range(latest, max(0, latest - count), -1):
            data = blobs.get(season) or get(season)
            if not data or b"category" not in data[:400]:
                print("   season %d: not available, skipped" % season)
                continue
            path = os.path.join(dest, "season%d.tsv" % season)
            with open(path + ".part", "wb") as fh:
                fh.write(data)
            os.replace(path + ".part", path)
            saved += 1
            print("   season %d   %4.1f MB" % (season, len(data) / 1e6))
    except (urllib.error.URLError, OSError, ValueError) as err:
        saved = with_git()
        if not saved:
            return manual_help(getattr(err, "reason", None) or err)
    print(" Saved %d season file(s) in %s" % (saved, dest))
    return saved > 0


# --------------------------------------------------------------------------
#  SEEDS AND BOARD BUILDING
# --------------------------------------------------------------------------
def resolve_seed(text):
    """Map free text such as 'africa geography questions' to a seed."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in ("", "any", "all", "general", "everything", "anything", "random", "real"):
        return "any"
    if cleaned in ("mixed", "mix", "themes", "six themes", "all themes", "mixed themes"):
        return "mixed"
    if cleaned.replace(" ", "") in THEMES:
        return cleaned.replace(" ", "")
    words = set(cleaned.split())
    best, best_score = None, 0
    for key, info in THEMES.items():
        score = 2 * len(words & (info["strong"] | {key})) + len(words & info["weak"])
        if score > best_score:
            best, best_score = key, score
    return best or "kw:" + cleaned


def seed_title(seed):
    if seed == "any":
        return "Any category"
    if seed == "mixed":
        return "Mixed (all six themes)"
    if seed.startswith("kw:"):
        return "Categories matching '%s'" % seed[3:]
    return THEMES[seed]["title"]


def filter_pool(items, seed):
    if seed == "any":
        return list(items)
    if seed == "mixed":
        return [it for it in items if it["themes"]]
    if seed.startswith("kw:"):
        return [it for it in items if seed[3:] in it["name"].lower()]
    return [it for it in items if seed in it["themes"]]


def _years_before(day, years):
    return "%04d%s" % (int(day[:4]) - years, day[4:])


def recent_first(pool, need, seen, taken=()):
    """Unplayed items from the newest clues, reaching further back only if needed.

    Returns (candidates, started_over). `need` counts distinct category names.
    """
    def names(items):
        return len({it["name"] for it in items})

    usable = [it for it in pool if it["key"] not in taken]
    fresh = [it for it in usable if it["key"] not in seen]
    started_over = False
    if names(fresh) < need:
        fresh, started_over = usable, names(usable) >= need and bool(seen)
    dates = [it["air"] for it in fresh if it["air"]]
    if not dates:
        return fresh, started_over
    newest = max(dates)
    for years in range(RECENT_YEARS, 80):
        cutoff = _years_before(newest, years)
        window = [it for it in fresh if (it["air"] or newest) >= cutoff]
        if names(window) >= need:
            return window, started_over
        if cutoff < min(dates):
            break
    return fresh, started_over


def deal(candidates, sizes, rng, used_names=None):
    """Deal categories onto boards: round-1 categories to the first board, etc."""
    candidates = list(candidates)
    rng.shuffle(candidates)
    used_names = set() if used_names is None else used_names
    used, boards = set(), []
    for number, size in enumerate(sizes, 1):
        board = []
        tests = (lambda c: c.get("round") == number, lambda c: c.get("round") is None,
                 lambda c: True)
        for allow_repeat_names in (False, True):
            for test in tests:
                for cat in candidates:
                    if len(board) == size:
                        break
                    if cat["key"] in used or not test(cat):
                        continue
                    if cat["name"] in used_names and not allow_repeat_names:
                        continue
                    board.append(cat)
                    used.add(cat["key"])
                    used_names.add(cat["name"])
        boards.append(board)
    return boards


def build_boards(cats, seed, sizes, seen, rng):
    """Returns (boards, started_over)."""
    total = sum(sizes)
    if seed != "mixed":
        candidates, started_over = recent_first(filter_pool(cats, seed), total, seen)
        return deal(candidates, sizes, rng), started_over
    # Mixed: the same number of categories from each theme on every board.
    boards, started_over = [[] for _ in sizes], False
    taken, used_names = set(), set()
    themes = list(THEMES)
    rng.shuffle(themes)
    per_theme = [max(1, size // len(themes)) for size in sizes]
    for theme in themes:
        candidates, again = recent_first(filter_pool(cats, theme), sum(per_theme), seen, taken)
        started_over = started_over or again
        for board, part in zip(boards, deal(candidates, per_theme, rng, used_names)):
            board += part
            taken.update(cat["key"] for cat in part)
    for board, size in zip(boards, sizes):          # top up if a theme ran short
        if len(board) < size:
            extra, _ = recent_first(filter_pool(cats, "mixed"), size - len(board), seen, taken)
            for cat in deal(extra, [size - len(board)], rng, used_names)[0]:
                board.append(cat)
                taken.add(cat["key"])
        rng.shuffle(board)
    return boards, started_over


def choose_final(finals, seed, seen, rng):
    pool = filter_pool(finals, seed) or (filter_pool(finals, "mixed") if seed != "any" else [])
    pool = pool or list(finals)
    if not pool:
        return None
    candidates, _ = recent_first(pool, min(3, len({f["name"] for f in pool})), seen)
    return rng.choice(candidates or pool)


# --------------------------------------------------------------------------
#  TERMINAL HELPERS
# --------------------------------------------------------------------------
class Quit(Exception):
    """Raised when the player quits or input ends."""


def paint(code, text):
    return "\033[%sm%s\033[0m" % (code, text) if USE_COLOR else text


def money(amount):
    return ("-$" if amount < 0 else "$") + format(abs(amount), ",")


def wrap(text, indent="   "):
    width = max(40, min(shutil.get_terminal_size((80, 24)).columns, 80) - 2)
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


def ask(prompt, timeout=None):
    """Read a line. With a timeout (terminals only) returns None when time runs out."""
    try:
        if timeout and sys.stdin.isatty():
            sys.stdout.write(prompt)
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if not ready:
                if termios:
                    try:
                        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
                    except (termios.error, OSError, ValueError):
                        pass
                print("\n" + paint("1;33", "  Time's up!"))
                return None
            line = sys.stdin.readline()
            if line == "":
                raise Quit()
            return line.strip()
        return input(prompt).strip()
    except EOFError:
        raise Quit()


# --------------------------------------------------------------------------
#  THE GAME
# --------------------------------------------------------------------------
class Game:
    def __init__(self, rounds, final, rng, timer=None, strict=False):
        self.rounds = rounds          # [(title, values, [category, ...]), ...]
        self.final = final
        self.rng = rng
        self.timer = timer
        self.strict = strict
        self.score = 0
        self.coryat = 0
        self.right = self.wrong = self.passed = 0
        self.by_cat = []              # [label, right, wrong, passed] per category
        self.missed = []              # (label, clue text, response, what you typed)
        self.explained = set()        # categories whose host comment has been shown

    # ---- flow ----------------------------------------------------------
    def run(self):
        for index, (title, values, cats) in enumerate(self.rounds):
            self.play_round(index, title, values, cats)
        if self.final:
            self.play_final()

    def play_round(self, index, title, values, cats):
        open_cells = [[True] * 5 for _ in cats]
        doubles = self.place_daily_doubles(len(cats), 1 if index == 0 else 2)
        stats = [[cat["name"], 0, 0, 0] for cat in cats]
        self.by_cat += stats
        last = 0
        while any(any(column) for column in open_cells):
            self.show_board(title, values, cats, open_cells)
            col, row = self.pick(values, cats, open_cells, last)
            open_cells[col][row] = False
            last = col
            self.play_clue(cats[col], row, values[row], (col, row) in doubles,
                           index, values[-1], stats[col])
        print()
        print(paint("1;34", " End of the %s. Score: %s" % (title, money(self.score))))

    def place_daily_doubles(self, columns, count):
        weights = [1, 9, 26, 39, 25]          # rarely on the top row, as on the show
        chosen = self.rng.sample(range(columns), min(count, columns))
        return {(col, self.rng.choices(range(5), weights)[0]) for col in chosen}

    def show_board(self, title, values, cats, open_cells):
        print()
        print(paint("1;34", "=" * 72))
        print(paint("1;34", " " + title) + "     Score: " + paint("1", money(self.score)))
        print(paint("1;34", "=" * 72))
        for i, cat in enumerate(cats):
            cells = "".join("%7s" % (money(values[r]) if open_cells[i][r] else "---")
                            for r in range(5))
            name = cat["name"] if len(cat["name"]) <= 32 else cat["name"][:29] + "..."
            print(" %d. %-32s%s" % (i + 1, name, cells))
        print()

    def pick(self, values, cats, open_cells, last):
        while True:
            raw = ask(" Pick (e.g. '3 600'), Enter = next clue, q = quit: ").lower()
            if raw in ("q", "quit", "exit"):
                if ask(" Quit this game? It won't count as a score. (y/N): ").lower().startswith("y"):
                    raise Quit()
                continue
            if raw == "":
                order = [last] + [i for i in range(len(cats)) if i != last]
                for col in order:
                    for row in range(5):
                        if open_cells[col][row]:
                            return col, row
            tokens = re.findall(r"[a-z]+|\d+", raw.replace(",", "").replace("$", ""))
            col = None
            if tokens and tokens[0].isdigit():
                col = int(tokens[0]) - 1
            elif tokens and len(tokens[0]) == 1:
                col = ord(tokens[0]) - ord("a")
            if col is None or not 0 <= col < len(cats):
                print("  Type a category number and a dollar value, e.g. 3 600")
                continue
            if len(tokens) < 2:
                rows = [r for r in range(5) if open_cells[col][r]]
                if not rows:
                    print("  That category is finished.")
                    continue
                return col, rows[0]
            amount = int(tokens[1]) if tokens[1].isdigit() else -1
            if amount in values:
                row = values.index(amount)
            elif 1 <= amount <= 5:
                row = amount - 1
            else:
                print("  Values this round: " + ", ".join(money(v) for v in values))
                continue
            if not open_cells[col][row]:
                print("  That clue has already been played.")
                continue
            return col, row

    def get_wager(self, low, high):
        while True:
            raw = ask("  Your wager (%s to %s, or 'max'): " % (money(low), money(high)))
            raw = raw.lower().replace("$", "").replace(",", "").strip()
            if raw in ("max", "all", "true daily double"):
                return high
            if raw.isdigit() and low <= int(raw) <= high:
                return int(raw)
            print("  Enter a whole-dollar amount in that range.")

    def get_response(self, seconds):
        timed = seconds and sys.stdin.isatty()
        return ask("  Your response%s: " % (" (%ds)" % seconds if timed else ""), seconds)

    # ---- judging -------------------------------------------------------
    def judge(self, answer, clue, must_answer, lenient_phrasing):
        display, accepted = clue[1], accepted_answers(clue)
        if not answer:
            if must_answer:
                print(paint("1;31", "  No response. ") + "Correct response: " + paint("1", display))
                return "wrong"
            print("  Pass. Correct response: " + paint("1", display))
            return "pass"
        correct = is_correct(answer, accepted)
        if correct and self.strict and not QUESTION_RE.match(answer):
            if lenient_phrasing:
                print("  (Remember to phrase it as a question - that only slides in the first round.)")
            else:
                print(paint("1;31", "  Right fact, but not phrased as a question - ruled incorrect. ")
                      + paint("1", display))
                return "wrong"
        if correct:
            print(paint("1;32", "  Correct! ") + display)
            return "right"
        print(paint("1;31", "  Incorrect. ") + "Correct response: " + paint("1", display))
        again = ask("  Enter = continue, o = override (I was right): ")
        if again.lower().startswith("o"):
            print("  Overridden - scored as correct.")
            return "right"
        return "wrong"

    def tally(self, verdict, stats, label, clue, answer):
        if verdict == "right":
            self.right += 1
        elif verdict == "wrong":
            self.wrong += 1
        else:
            self.passed += 1
        stats[{"right": 1, "wrong": 2, "pass": 3}[verdict]] += 1
        if verdict != "right":
            self.missed.append((label, clue[0], clue[1], answer or "(no response)"))

    def play_clue(self, cat, row, value, daily_double, round_index, round_max, stats):
        clue = cat["clues"][row]
        origin = clue[3] if len(clue) > 3 else None
        header = " %s for %s" % (cat["name"], money(value))
        if cat.get("air") and not origin:
            header += "   (aired %s)" % cat["air"]
        print()
        print(paint("1;36", header))
        if origin:
            print(paint("36", "   from %s (aired %s)" % (origin["name"], origin["air"])))
            if origin["comment"]:
                print(paint("2", wrap(origin["comment"])))
        elif cat.get("comment") and cat["key"] not in self.explained:
            self.explained.add(cat["key"])
            print(paint("2", wrap(cat["comment"])))
        wager = value
        if daily_double:
            print(paint("1;33", " *** DAILY DOUBLE! ***") + "   Your score: " + money(self.score))
            wager = self.get_wager(5, max(self.score, round_max))
        print()
        print(paint("1", wrap(clue[0])))
        print()
        answer = self.get_response(self.timer)
        verdict = self.judge(answer, clue, must_answer=daily_double,
                             lenient_phrasing=(round_index == 0 and not daily_double))
        if verdict == "right":
            self.score += wager
            self.coryat += value
        elif verdict == "wrong":
            self.score -= wager
            if not daily_double:
                self.coryat -= value
        if origin:
            label = "%s %s, aired %s" % (origin["name"], money(value), origin["air"])
        else:
            label = "%s %s" % (cat["name"], money(value))
            if cat.get("air"):
                label += ", aired %s" % cat["air"]
        self.tally(verdict, stats, label, clue, answer)
        if verdict != "pass":
            change = wager if verdict == "right" else -wager
            print("  %s%s  ->  score %s" % ("+" if change > 0 else "-", money(abs(change)),
                                            money(self.score)))

    def play_final(self):
        final = self.final
        print()
        print(paint("1;35", "=" * 72))
        print(paint("1;35", " FINAL JEOPARDY!") + "     Score: " + paint("1", money(self.score)))
        print(paint("1;35", "=" * 72))
        print(" Category: " + paint("1;36", final["name"])
              + ("   (aired %s)" % final["air"] if final.get("air") else ""))
        if self.score > 0:
            wager = self.get_wager(0, self.score)
        else:
            wager = 0
            print("  With no money you'd sit out Final on the show - play it here for practice.")
        print()
        print(paint("1", wrap(final["clue"][0])))
        print()
        seconds = max(self.timer, 30) if self.timer else None
        answer = self.get_response(seconds)
        verdict = self.judge(answer, final["clue"], must_answer=True, lenient_phrasing=False)
        self.score += wager if verdict == "right" else -wager
        stats = ["FINAL: " + final["name"], 0, 0, 0]
        self.by_cat.append(stats)
        label = "FINAL - " + final["name"]
        if final.get("air"):
            label += ", aired %s" % final["air"]
        self.tally(verdict, stats, label, final["clue"], answer)

    # ---- wrap-up -------------------------------------------------------
    def summary(self):
        attempts = self.right + self.wrong
        pct = "%d%%" % round(100.0 * self.right / attempts) if attempts else "n/a"
        print()
        print(paint("1;34", "=" * 72))
        print(paint("1;34", " GAME OVER"))
        print(paint("1;34", "=" * 72))
        print(" Final score : " + paint("1", money(self.score)))
        print(" Coryat score: %s   (no wagering, no Final)" % money(self.coryat))
        print(" Responses   : %d right, %d wrong, %d passed   (accuracy when answering: %s)"
              % (self.right, self.wrong, self.passed, pct))
        print()
        print(" By category (right / wrong / passed):")
        for name, right, wrong, passed in self.by_cat:
            print("   %-40s %d / %d / %d" % (name[:40], right, wrong, passed))
        if self.missed:
            print()
            print(paint("1", " Clues to study:"))
            for label, text, display, typed in self.missed:
                print()
                print(paint("36", "  [%s]" % label))
                print(wrap(text, "    "))
                print("    -> " + paint("1", display) + "   (you: %s)" % typed)


# --------------------------------------------------------------------------
#  SAVED DATA: high scores and which categories you have played
# --------------------------------------------------------------------------
def default_data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "jtrainer")


def load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, type(fallback)) else fallback
    except (OSError, ValueError):
        return fallback


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path + ".part", "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(path + ".part", path)
        return True
    except OSError as err:
        print(" (Could not save %s: %s)" % (path, err))
        return False


def show_table(scores, key, label, newest=None):
    rows = sorted((s for s in scores if s.get("key") == key),
                  key=lambda s: s.get("score", 0), reverse=True)[:10]
    print()
    print(paint("1;33", " HIGH SCORES - " + label))
    if not rows:
        print("   (none yet)")
    for rank, s in enumerate(rows, 1):
        mark = "  <-- this game" if s is newest else ""
        print("  %2d. %9s   Coryat %8s   %-12s %s%s"
              % (rank, money(s.get("score", 0)), money(s.get("coryat", 0)),
                 str(s.get("name", "?"))[:12], s.get("date", ""), mark))
    return rows


def show_all_scores(scores):
    if not scores:
        print("No high scores yet - play a game first.")
        return
    seen = []
    for s in scores:
        if s.get("key") not in seen:
            seen.append(s.get("key"))
    for key in seen:
        label = next(s.get("label", key) for s in scores if s.get("key") == key)
        show_table(scores, key, label)
    print()


# --------------------------------------------------------------------------
#  COMMANDS
# --------------------------------------------------------------------------
def date_span(items):
    dates = []
    for item in items:
        origins = [c[3]["air"] for c in item.get("clues", []) if len(c) > 3]
        dates += origins or ([item["air"]] if item.get("air") else [])
    return "%s to %s" % (min(dates), max(dates)) if dates else ""


def run_check(cats, finals, stats, from_show):
    """Validate the built-in practice set and summarize whatever is loaded."""
    problems, seen_text = [], set()
    practice_cats, practice_finals = builtin_pool()
    for cat in practice_cats:
        if len(cat["clues"]) != 5:
            problems.append("%s: has %d clues, expected 5" % (cat["name"], len(cat["clues"])))
        for clue in cat["clues"]:
            text, display, accepted = clue[0], clue[1], clue[2]
            if not text.strip() or not is_correct(display, accepted):
                problems.append("%s: unanswerable clue -> %s" % (cat["name"], display))
            if text in seen_text:
                problems.append("%s: duplicate clue text -> %s" % (cat["name"], text[:50]))
            seen_text.add(text)
    for final in practice_finals:
        text, display, accepted = final["clue"]
        if not text.strip() or not is_correct(display, accepted):
            problems.append("FINAL %s: unanswerable clue -> %s" % (final["name"], display))
    print("Built-in practice set: %d categories, %d clues, %d Final clues"
          % (len(practice_cats), sum(len(c["clues"]) for c in practice_cats),
             len(practice_finals)))
    if from_show:
        print("Show clues loaded:     %d categories, %d clues, %d Final clues, aired %s"
              % (len(cats), 5 * len(cats), len(finals), date_span(cats)))
        print("  (includes %d mix categories; left out: %d incomplete, %d picture-based, "
              "%d with time-sensitive wording)"
              % (stats.get("mixes", 0), stats.get("incomplete", 0), stats.get("visual", 0),
                 stats.get("dated", 0)))
        for key, info in THEMES.items():
            print("  %-24s %5d categories, %3d finals"
                  % (info["title"], len(filter_pool(cats, key)), len(filter_pool(finals, key))))
    else:
        print("Show clues loaded:     none (run --fetch)")
    if problems:
        print("\nProblems found:")
        for line in problems:
            print("  - " + line)
        return 1
    print("Practice set data OK.")
    return 0


def list_seeds(cats, from_show):
    source = "show clues, aired %s" % date_span(cats) if from_show else "built-in practice set"
    print("Seeds (use with --seed) - %s:\n" % source)
    for key in list(THEMES) + ["mixed", "any"]:
        pool = sorted(filter_pool(cats, key), key=lambda c: c["air"] or "", reverse=True)
        print(paint("1", "  %-12s %s  (%d categories)" % (key, seed_title(key), len(pool))))
        if key in THEMES:
            names = []
            for cat in pool:
                if cat["name"] not in names:
                    names.append(cat["name"])
            more = " ..." if len(names) > 30 else ""
            print(wrap("newest: " + "; ".join(names[:30]) + more, "      "))
        print()
    print("Any other text filters by category name, e.g. --seed opera")


def choose_seed_menu(cats):
    print(paint("1;34", "\n J! TRAINER") + "  -  pick a seed:\n")
    keys = list(THEMES) + ["mixed", "any"]
    for i, key in enumerate(keys, 1):
        print("  %d. %-26s (%d categories)" % (i, seed_title(key), len(filter_pool(cats, key))))
    while True:
        raw = ask("\n Seed number or name: ")
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            return keys[int(raw) - 1]
        if raw and not raw.isdigit():
            return resolve_seed(raw)


def main():
    global USE_COLOR
    parser = argparse.ArgumentParser(
        description="J! TRAINER - one-player Jeopardy! trainer for the terminal.",
        epilog="Seeds: " + ", ".join(list(THEMES) + ["mixed", "any"])
               + ". Free text works too, e.g. --seed \"africa geography questions\".")
    parser.add_argument("words", nargs="*", metavar="SEED",
                        help="seed text (same as --seed)")
    parser.add_argument("-s", "--seed", "--theme", nargs="*", metavar="TEXT",
                        help="question-set seed / theme (see --list)")
    parser.add_argument("--quick", action="store_true", help="one round plus Final")
    parser.add_argument("--timer", type=int, metavar="SECONDS",
                        help="time limit per response (Final gets at least 30s)")
    parser.add_argument("--strict", action="store_true",
                        help="responses must be phrased as a question")
    parser.add_argument("--since", type=int, metavar="YEAR",
                        help="only use show clues that aired in YEAR or later")
    parser.add_argument("--fetch", nargs="?", type=int, const=DEFAULT_FETCH, metavar="N",
                        help="download the N newest seasons of show clues (default %d)"
                             % DEFAULT_FETCH)
    parser.add_argument("--practice", action="store_true",
                        help="use the built-in practice set instead of show clues")
    parser.add_argument("--clues", action="append", metavar="PATH", default=[],
                        help="extra clue file or folder (TSV/CSV/JSON); repeatable")
    parser.add_argument("--name", help="name for the high-score table (default: $USER)")
    parser.add_argument("--shuffle", type=int, metavar="N",
                        help="number that makes the board reproducible (same N = same game)")
    parser.add_argument("--list", action="store_true", help="list seeds and categories")
    parser.add_argument("--scores", action="store_true", help="show high scores")
    parser.add_argument("--check", action="store_true", help="summarize and validate the clue data")
    parser.add_argument("--reset-seen", action="store_true",
                        help="forget which categories you have already played")
    parser.add_argument("--data-dir", metavar="PATH",
                        help="where clues, scores and history are kept "
                             "(default: ~/.local/share/jtrainer)")
    parser.add_argument("--no-color", action="store_true", help="plain output, no ANSI colors")
    parser.add_argument("--version", action="version", version="J! TRAINER " + VERSION)
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    USE_COLOR = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    data_dir = args.data_dir or default_data_dir()
    clues_dir = os.path.join(data_dir, "clues")
    scores_path = os.path.join(data_dir, "highscores.json")
    seen_path = os.path.join(data_dir, "seen.json")
    here = os.path.dirname(os.path.abspath(__file__))

    if args.scores:
        show_all_scores(load_json(scores_path, []))
        return 0
    if args.reset_seen:
        save_json(seen_path, [])
        print(" Play history cleared.")
    if args.fetch is not None:
        if not fetch_seasons(clues_dir, args.fetch):
            return 1

    # ---- load clues ------------------------------------------------------
    files = clue_files([clues_dir, os.path.join(here, "clues")] + args.clues)
    try:
        if not files and not args.practice and interactive and not (args.check or args.list):
            print("\n No show clues are downloaded yet.")
            reply = ask(" Download the %d newest seasons now (about 14 MB)? [Y/n]: "
                        % DEFAULT_FETCH).lower()
            if not reply.startswith("n") and fetch_seasons(clues_dir, DEFAULT_FETCH):
                files = clue_files([clues_dir])
    except (Quit, KeyboardInterrupt):
        print()
        return 1
    cats, finals, stats, from_show = [], [], {}, False
    if files and not args.practice:
        cats, finals, stats = load_show_pool(files, args.since,
                                             os.path.join(data_dir, "cache.json"))
        from_show = bool(cats)
        if not from_show:
            print(" No complete categories found in the clue files%s."
                  % (" from %d on" % args.since if args.since else ""))
    if not from_show:
        cats, finals = builtin_pool()
        if not args.practice and not (args.check or args.list):
            print(" Using the built-in practice set (written for this trainer, not from the show).")
            print(" For real show clues run:  python3 %s --fetch" % os.path.basename(__file__))

    if args.check:
        return run_check(cats, finals, stats, from_show)
    if args.list:
        list_seeds(cats, from_show)
        return 0
    if args.fetch is not None and not interactive and args.seed is None and not args.words:
        return 0

    # ---- choose seed and build the boards --------------------------------
    try:
        if args.seed is not None or args.words:
            seed = resolve_seed(" ".join((args.seed or []) + args.words))
        elif interactive:
            seed = choose_seed_menu(cats)
        else:
            seed = "any"
    except (Quit, KeyboardInterrupt):
        print()
        return 1
    if seed == "any" and not from_show:
        seed = "mixed"                      # the practice set only has the six themes

    rng = random.Random(args.shuffle)
    seen = set(load_json(seen_path, []))
    available = len({c["name"] for c in filter_pool(cats, seed)})
    quick = args.quick
    if available < 6:
        print(" Seed '%s' matches only %d categories (6 needed)." % (seed_title(seed), available))
        print(" Try --list, a different seed%s." % (", or --fetch more seasons" if from_show else ""))
        return 2
    if available < 12 and not quick:
        print(" Only %d categories match this seed - playing a one-round game." % available)
        quick = True
    sizes = [6] if quick else [6, 6]
    boards, started_over = build_boards(cats, seed, sizes, seen, rng)
    if any(len(board) < size for board, size in zip(boards, sizes)):
        print(" Not enough categories for seed '%s'. Try --list." % seed_title(seed))
        return 2
    if started_over:
        print(" You have played every category for this seed - starting over with repeats.")
    rounds = [("JEOPARDY! ROUND", ROUND1_VALUES, boards[0])]
    if not quick:
        rounds.append(("DOUBLE JEOPARDY! ROUND", ROUND2_VALUES, boards[1]))
    final = choose_final(finals, seed, seen, rng)

    played = [cat for board in boards for cat in board]
    seen.update(cat["key"] for cat in played)
    if final:
        seen.add(final["key"])
    save_json(seen_path, sorted(seen))

    game = Game(rounds, final, rng, timer=args.timer, strict=args.strict)
    mode = "quick game" if quick else "full game"
    print()
    print(paint("1;34", " J! TRAINER") + "   seed: " + paint("1", seed_title(seed)) + "   (%s)" % mode)
    if from_show:
        print(" Clues from the show, aired %s." % date_span(played))
    else:
        print(" Built-in practice clues (not from the show).")
    print(" Type a response and press Enter. Enter alone = pass (no penalty).")
    print(" Daily Doubles and Final must be answered. Small typos are forgiven.")
    if args.strict:
        print(" Strict mode: phrase every response as a question (What is...? Who is...?).")
    if args.timer:
        print(" Timer: %d seconds per response." % args.timer)

    try:
        game.run()
    except (Quit, KeyboardInterrupt):
        print("\n\n Game abandoned - no score recorded. Score so far: %s" % money(game.score))
        return 1

    game.summary()
    source = "show" if from_show else "practice"
    key = "%s|%s|%s" % (seed, "quick" if quick else "full", source)
    label = "%s (%s, %s clues)" % (seed_title(seed), mode, source)
    entry = {"key": key, "label": label, "score": game.score, "coryat": game.coryat,
             "right": game.right, "wrong": game.wrong, "passed": game.passed,
             "name": args.name or os.environ.get("USER") or "player",
             "date": date.today().isoformat()}
    scores = load_json(scores_path, [])
    previous_best = max((s.get("score", 0) for s in scores if s.get("key") == key), default=None)
    scores.append(entry)
    save_json(scores_path, scores)
    if previous_best is None:
        print(paint("1;32", "\n First score on the board for this seed!"))
    elif game.score > previous_best:
        print(paint("1;32", "\n NEW HIGH SCORE! (previous best: %s)" % money(previous_best)))
    else:
        print("\n Best to beat: %s" % money(previous_best))
    show_table(scores, key, label, newest=entry)
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
