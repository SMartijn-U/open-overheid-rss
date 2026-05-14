import requests
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone

API_URL = (
    "https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek"
    "?zoektekst="
    "&start=0"
    "&aantalResultaten=20"
    "&informatiecategorie=agenda%25E2%2580%2599s%2520en%2520besluitenlijsten%2520bestuurscolleges"
    "&organisatie=ministerie%2520van%2520Algemene%2520Zaken"
)

# API ophalen
response = requests.get(API_URL)
response.raise_for_status()

data = response.json()

# Feed aanmaken
fg = FeedGenerator()

fg.title("Open Overheid RSS")
fg.link(href=API_URL)
fg.description("Nieuwe openbaarmakingen")
fg.language("nl")

# Resultaten ophalen
results = data.get("resultaten", [])

# Nieuwste eerst sorteren
results = sorted(
    results,
    key=lambda x: x.get("document", {}).get("openbaarmakingsdatum", ""),
    reverse=True
)

# Entries toevoegen
for item in results:

    document = item.get("document", {})

    title = document.get("titel", "Geen titel")
    url = document.get("pid", "")
    pubdate = document.get("openbaarmakingsdatum")
    publisher = document.get("publisher", "")

    fe = fg.add_entry()

    fe.title(title)
    fe.link(href=url)
    fe.guid(url)
    fe.description(publisher)

    if pubdate:
        try:
            dt = datetime.fromisoformat(pubdate)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            fe.pubDate(dt)

        except Exception as e:
            print(f"Datumfout bij {title}: {e}")

# RSS-bestand schrijven
fg.rss_file("feed.xml")

print("feed.xml gemaakt met", len(results), "items")