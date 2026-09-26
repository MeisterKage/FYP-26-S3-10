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
