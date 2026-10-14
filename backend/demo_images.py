"""Demo cover images: openly licensed photos from Wikimedia Commons.

    py demo_images.py      # after seed.py; needs internet access

Each photo is fetched from Commons, run through the same processing as a writer's
upload (app/images.py: decoded, metadata stripped, resized), stored as that
article's writer's upload, and attached with alt text and a credit naming the
photographer and licence. Safe to run again: an article that already has a
cover image is skipped.

Several photos illustrate a story rather than depict its exact event, as news
file photos do. The alt text describes only what is visible, so it never claims
a place or an event the photo does not show.
"""
from __future__ import annotations

import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from app import create_app
from app.extensions import db
from app.images import process
from app.models import Article, ArticleImage

USER_AGENT = "WollongongNewsDemo/1.0 (university student project; demo images)"

# (article title, Commons file, photographer as credited, licence, alt text)
PHOTOS = [
    ("Wollongong council opens consultation on a revised city centre plan",
     "File:CrownStreetMall WollongongNSW.jpg", "ColonelLight", "CC0",
     "Stone sculptures in a paved pedestrian mall lined with shops."),
    ("Illawarra escarpment walking tracks reopen after landslip repairs",
     "File:The Illawarra Escarpment Track - panoramio (4).jpg", "Maurice van Creij", "CC BY 3.0",
     "A walking track running through dense eucalyptus bushland."),
    ("Wollongong prepares to host a regional surf life saving carnival",
     "File:North Beach, Wollongong, December 2025 01.jpg", "DaHuzyBru", "CC BY-SA 4.0",
     "A beachfront lawn and promenade leading down to a wide sandy beach under cloud."),
    ("Port Kembla precinct courts renewable manufacturing investors",
     "File:13 Industry of Australia - Steelworks of BlueScope Steel Limited company in Port Kembla, Australia.jpg",
     "Marek Ślusarczyk (Tupungato)", "CC BY 3.0",
     "Steelworks chimneys and plumes of steam behind rows of suburban houses."),
    ("University researchers map seagrass recovery along the Illawarra coast",
     "File:Seagrass , Posidonia oceanica.jpg", "Milorad Mikota", "CC BY-SA 4.0",
     "A dense seagrass meadow underwater, lit from above."),
    ("New Zealand extends predator trapping network across two more regions",
     "File:Fairy Falls Track 20241227 125955.jpg", "Prosperosity", "CC BY 4.0",
     "Tree ferns and tall native trees in a forest canopy under a blue sky."),
    ("Dairy export prices lift as New Zealand co-operatives report stronger orders",
     "File:Dairy cows grazing with visible graze line.jpg", "Halter", "CC BY-SA 4.0",
     "A herd of black and white dairy cows grazing on a green pasture."),
    ("Wellington club confirms stadium upgrade ahead of the rugby season",
     "File:Wellington Westpac Stadium, 23 April 2005.jpg", "Phillip Capper", "CC BY 2.0",
     "A round stadium beside a harbour container port, with hills behind."),
    ("Singapore expands public trials of autonomous shuttle buses",
     "File:Queen Street Bus Terminal 2.JPG", "Terence Ong", "CC BY 2.5",
     "Buses parked at a city bus terminal with high-rise buildings behind."),
    ("Singapore port handles record transhipment volumes this quarter",
     "File:The new container ship OOCL Singapore on her maiden voyage with destination Port of Hamburg.jpg",
     "Buonasera", "CC BY-SA 3.0",
     "A large container ship stacked high with shipping containers."),
    ("Japan's earthquake early warning network adds offshore sensors",
     "File:三陸海岸の青い空と海 (Sanriku coast with blue sky and sea) 07 Sep, 2014 - panoramio.jpg",
     "Hiroaki Kaneko", "CC BY-SA 3.0",
     "A rocky coastline with sea stacks under a wide blue sky."),
    ("Tokyo hospitals trial robotic lifting assistance in elderly care wards",
     "File:Minato City, Tokyo, Japan.jpg", "David Kernan", "CC BY 4.0",
     "A dense city skyline of towers in daylight, with a red and white tower among them."),
    ("UK councils gain new powers to convert empty shops into housing",
     "File:Empty shops, 33 High Street, Pershore - geograph.org.uk - 6551997.jpg",
     "Jeff Gogarty", "CC BY-SA 2.0",
     "A row of older high street shopfronts, several of them empty."),
    ("UK water companies ordered to publish sewage overflow data daily",
     "File:London MMB »0A1 River Thames.jpg", "mattbuck", "CC BY-SA 4.0",
     "A wide river with moored vessels and an industrial riverbank."),
    ("UK polar researchers retrieve their deepest ice core yet",
     "File:Antarctica WAIS Divide Field Camp 10.jpg", "Eli Duke", "CC BY-SA 2.0",
     "A cylinder of ice core resting in a metal trough in a laboratory."),
    ("US airlines add capacity on transpacific routes to Australia",
     "File:Los Angeles International Airport by Don Ramey Logan.jpg", "Don Ramey Logan",
     "CC BY-SA 4.0", "An aerial view of a large airport with runways and terminals."),
    ("US coastal cities publish shared flood maps for the first time",
     "File:Sandy Damage Bay Bkwy 2 jeh.JPG", "Jim.henderson", "CC BY-SA 3.0",
     "A storm-damaged waterfront path with broken paving, and cyclists walking past."),
    ("Japanese carmakers agree a shared battery recycling standard",
     "File:18650 and 21700 lithium ion battery cell.jpg", "Sevenethics", "CC0",
     "Two cylindrical lithium-ion battery cells in yellow holders."),
    ("Parliament passes revised data protection framework",
     "File:Parliament House at dusk, Canberra ACT.jpg", "Thennicke", "CC BY-SA 4.0",
     "Parliament House in Canberra lit up at dusk, its flagpole above and a reflecting pool in front."),
    ("Regional startups raise record funding despite slowdown",
     "File:Skyline of the Central Business District of Singapore with Esplanade Bridge in the evening.jpg",
     "Basile Morin", "CC BY-SA 4.0",
     "Office towers of Singapore's business district above the water at dusk, with a bridge in front."),
    ("Grid operators report record renewable share in Q3",
     "File:Broken Hill solar plant aerial.jpg", "Jeremy Buckingham", "CC BY 2.0",
     "An aerial view of a large solar plant laid out across flat, dry scrubland."),
    ("Semiconductor shortage eases as new fabrication capacity opens",
     "File:A semiconductor wafer being removed from processing equipment.jpg", "Purdue Engineering",
     "CC BY 4.0", "A gloved hand lifts a semiconductor wafer out of processing equipment."),
    ("Public transport ridership returns to pre-pandemic levels",
     "File:Auckland electric train at Newmarket station, April 2014.jpg", "Sitedmambo", "CC BY-SA 3.0",
     "A yellow and grey electric train at a station platform, with passengers walking alongside."),
    ("Researchers publish open dataset on coastal erosion",
     "File:Beach erosion at the mouth of Noosa River, Noosa North Shore beach, Queensland, Australia 01.jpg",
     "Chris Olszewski", "CC BY-SA 4.0",
     "A steep, freshly eroded sand bank along a beach, with footprints and tyre tracks on the sand below."),
    ("Health ministry expands subsidised screening programme",
     "File:Blood pressure check.jpg", "Delael", "CC BY-SA 4.0",
     "A digital blood pressure monitor showing a reading, with its cuff wrapped around an upper arm."),
    ("Local league announces revised season structure",
     "File:Broncos vs. Dragons 03.jpg", "Anke from Brisbane, Australia", "CC BY 2.0",
     "Rugby league players in maroon and in red and white jerseys during a match, in front of a packed crowd."),
    ("Central bank holds rates steady for third quarter",
     "File:RBNZ Building Wellington.jpg", "Panamitsu", "CC BY-SA 4.0",
     "The white tower of the Reserve Bank of New Zealand building in Wellington against a blue sky."),
    ("Universities pilot shared research computing cluster",
     "File:Pleiades supercomputer racks 2.jpg", "Oleg Alexandrov", "CC BY-SA 4.0",
     "A long aisle between rows of black supercomputer racks."),
    ("Coastal reclamation project clears environmental review",
     "File:Marina Bay Golf Course, Marina East, Singapore - 20120721.jpg", "Nicolas Lannuzel", "CC BY-SA 2.0",
     "A wide green golf course at Marina East, with Singapore's city skyline in the distance under a blue sky."),
    ("Retail sector reports uneven recovery across segments",
     "File:Eastland Mall interior, Tulsa, OK.jpg", "Janice Waltzer", "CC BY 2.0",
     "A quiet shopping mall corridor under a skylight roof, with few shoppers."),
    ("New guidelines issued for clinical trial transparency",
     "File:Medical Research Council, Laboratory of Molecular Biology - geograph.org.uk - 3016826.jpg",
     "David P Howard", "CC BY-SA 2.0",
     "The Medical Research Council's Laboratory of Molecular Biology in Cambridge, seen across a green field."),
    ("Wind capacity overtakes coal in regional generation mix",
     "File:Turbines at Crookwell 2 Wind Farm April 2026.jpg", "Nick-D", "CC BY-SA 4.0",
     "Wind turbines spread across rolling farmland, with a road winding between the paddocks."),
    ("Small businesses adopt digital payments at record pace",
     "File:Cashless-Payment-Devices CreditCard-and-Code-payment.jpg", "RuinDig/Yuki Uchida", "CC BY 4.0",
     "A card payment terminal and a QR code scanner on a shop counter, beside payment signs in Japanese."),
    ("Air quality index improves after emissions rules tighten",
     "File:Shibuya and Mount Fuji seen from Roppongi Hills.jpg", "Syced", "CC0",
     "A clear view across Tokyo's dense skyline to snow-capped Mount Fuji on the horizon."),
    ("National team qualifies after decisive away fixture",
     "File:City of Manchester Stadium Crowd Against Hull.jpg", "AGilhooley", "CC BY-SA 3.0",
     "Football supporters filling the stands of a large stadium."),
    ("Singapore clinics pilot shared electronic records for chronic care",
     "File:Telemedicine Consult.jpg", "Intel Free Press", "CC BY-SA 2.0",
     "A doctor at a desk works across several computer screens showing medical images and a video call."),
    ("US states agree a common framework for data broker registration",
     "File:BalticServers data center.jpg", "BalticServers.com", "CC BY-SA 3.0",
     "Racks of computer servers in a data centre, lit with blue lights."),
    ("US college sport adopts new athlete revenue-sharing rules",
     "File:Geneva College Reeves Stadium stands.jpg", "Claybedmcc", "CC0",
     "A college football game on an artificial turf field, watched by a crowd in the stands."),
    ("US rural hospitals expand telehealth links to specialist centres",
     "File:Оцінка ефективності телемедицини для навчання пікфлоуметрії пацієнтів із захворюваннями органів дихання.jpg",
     "Mariia Tsyben", "CC0",
     "A doctor in a white coat with a stethoscope holds a phone at his desk beside an open laptop."),
    ("Malaysian chip packaging plants expand as global orders recover",
     "File:Clean room.jpg", "NASA Glenn Research Center", "public domain",
     "A semiconductor clean room lit in yellow, with a worker in a protective suit at the equipment."),
    ("Malaysia widens protection for peat swamp forests in Borneo",
     "File:Peat Forest Swamp (10712654875).jpg", "Ruanda Agung Sugardiman/AusAID", "CC BY 2.0",
     "An aerial view of a river winding through dense, flat swamp forest."),
    ("Kuala Lumpur prepares to host a regional badminton championship",
     "File:2018-10-12 Badminton Mixed International Team Bronze medal match 6 at 2018 Summer Youth Olympics by Sandro Halank–019.jpg",
     "Sandro Halank", "CC BY-SA 4.0",
     "Two players lunge for the shuttle during a badminton doubles match on an indoor court."),
    ("Penang councillors approve a public transit corridor plan for the island",
     "File:Skyline of George Town, Penang at dusk March 2025-03.jpg", "HundenvonPenang", "CC BY-SA 4.0",
     "High-rise towers of George Town, Penang, at dusk."),
    ("Chinese electric car makers expand battery swap station networks",
     "File:NIO Battery Swap station in use at Oslo, Norway.jpg", "Premeditated", "CC BY-SA 4.0",
     "A battery swap station for electric cars, a long grey building with a car parked beside it."),
    ("Chinese city trials sponge park design to absorb summer floods",
     "File:Tianjin Qiaoyuan Park (Tianjin City, built 2008).jpg", "Mydogistiaotiaohu", "CC BY-SA 4.0",
     "An aerial view of a park of ponds and wetland planting, crossed by winding red paths."),
    ("Shanghai clinics extend evening hours to ease hospital queues",
     "File:Shanghai Night Street (29214289206).jpg", "Михаил Лазарев", "CC BY 2.0",
     "A brightly lit shop on a Shanghai street at night, with scooters parked along the pavement."),
    ("Bengaluru start-ups build phone tools for small farmers",
     "File:Farmer manually harvesting rice in Raichur, Karnataka.jpg", "Nanditha Gogate, WELL Labs",
     "CC BY-SA 4.0", "A farmer bends to harvest a golden field of rice by hand."),
    ("Kerala expands home visits for elderly patients with chronic illness",
     "File:Blood pressure measurement Manila CNE 01.jpg", "CNEcija12345", "CC BY-SA 4.0",
     "A health worker checks a seated man's blood pressure with an arm cuff."),
    ("Mumbai marathon adds a wheelchair race to its programme",
     "File:David Bizet - Marathon de Paris 2014.jpg", "Marie-Lan Nguyen", "CC BY 3.0",
     "A wheelchair racer and a runner pass spectators during a city marathon."),
    ("Wollongong councillors back a trial of later night bus services",
     "File:Wollongong station bus stop.jpg", "WGong1", "CC BY-SA 4.0",
     "The covered bus stops beside Wollongong station, with a pedestrian crossing in front."),
    ("Scottish councils publish their first shared climate budget",
     "File:Glasgow City Chambers Exterior.jpg", "Michael D Beckwith", "CC0",
     "Glasgow City Chambers, an ornate Victorian building, seen across George Square."),
    ("Singapore opens consultation on protections for food delivery riders",
     "File:Food delivery - Flickr - GeorgeTan ^2...thanks for millionth support.jpg", "GeorgeTan",
     "public domain", "A food delivery rider in a green jacket and helmet rides a motorbike past cars."),
    ("Japanese prefectures pool funds to keep rural bus routes running",
     "File:Kakachu Hiratsuka88.jpg", "Cassiopeia sweet", "public domain",
     "A small bus travels along a road between green rice fields."),
]


def fetch(url: str) -> bytes:
    """Commons rate-limits eagerly, so pause before each request and back off on 429."""
    for attempt in range(6):
        time.sleep(2 + attempt * 10)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    raise RuntimeError(f"Rate limited fetching {url}")


def commons_url(file_title: str, width: int = 1600) -> str:  # re-sized to LARGE_WIDTH on processing
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": file_title,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": width,
    })
    data = json.loads(fetch(f"https://commons.wikimedia.org/w/api.php?{params}"))
    page = next(iter(data["query"]["pages"].values()))
    return page["imageinfo"][0]["thumburl"]


def main() -> None:
    added = 0
    for title, file_title, artist, licence, alt in PHOTOS:
        article = Article.query.filter_by(title=title).first()
        if article is None:
            print(f"  skip, no article: {title}")
            continue
        if article.cover_image_id:
            continue
        processed = process(fetch(commons_url(file_title)))
        image = ArticleImage(
            key=secrets.token_hex(16),
            owner_id=article.contributor_id,
            width=processed.width,
            height=processed.height,
            large=processed.large,
            thumb=processed.thumb,
        )
        db.session.add(image)
        db.session.flush()
        article.cover_image_id = image.id
        article.cover_image_alt = alt
        article.cover_image_credit = f"Photo: {artist}, {licence}, via Wikimedia Commons"
        db.session.commit()
        added += 1
        print(f"  {title[:60]}  ({len(processed.large) // 1024} KB)")
    print(f"Added {added} cover image(s).")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with create_app().app_context():
        main()
