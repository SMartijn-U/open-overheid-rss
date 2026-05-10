import requests
from feedgen.feed import FeedGenerator
from datetime import datetime

API_URL = "https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek?zoektekst=&start=0&aantalResultaten=20&informatiecategorie=agenda%25E2%2580%2599s%2520en%2520besluitenlijsten%2520bestuurscolleges&organisatie=ministerie%2520van%2520Algemene%2520Zaken"

response = requests.get(API_URL)
data = response.json()

fg = FeedGenerator()

fg.title("Open Overheid RSS")
fg.link(href=API_URL)
fg.description("Nieuwe openbaarmakingen")
fg.language("nl")

results = data.get("resultaten", [])

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
            fe.pubDate(dt)
        except:
            pass

fg.rss_file("feed.xml")

print("feed.xml gemaakt met", len(results), "items")