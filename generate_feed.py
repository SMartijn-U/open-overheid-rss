import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from feedgen.feed import FeedGenerator


API_URL = (
    "https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek"
    "?zoektekst="
    "&start=0"
    "&aantalResultaten=20"
    "&informatiecategorie=agenda%25E2%2580%2599s%2520en%2520besluitenlijsten%2520bestuurscolleges"
    "&organisatie=ministerie%2520van%2520Algemene%2520Zaken"
)

STATE_FILE = Path("data/rss_pubdates.json")
FEED_FILE = Path("feed.xml")


def utc_now_without_microseconds():
    """Geef de huidige UTC-tijd terug, afgerond op hele seconden."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def datetime_to_string(dt):
    """Sla een datetime genormaliseerd op als ISO 8601 in UTC."""
    return dt.astimezone(timezone.utc).isoformat()


def string_to_datetime(value):
    """Lees een opgeslagen ISO 8601-datum veilig terug."""
    if not value:
        return None

    try:
        normalized_value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized_value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (TypeError, ValueError):
        return None


def load_pubdate_state():
    """Lees eerder toegekende pubDates uit het statusbestand."""
    if not STATE_FILE.exists():
        print(f"Statusbestand {STATE_FILE} bestaat nog niet.")
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            state = json.load(file)

        if not isinstance(state, dict):
            raise ValueError("De inhoud van het statusbestand is geen object.")

        valid_state = {}

        for guid, pubdate_string in state.items():
            dt = string_to_datetime(pubdate_string)

            if dt is None:
                print(f"Ongeldige opgeslagen pubDate overgeslagen: {guid}")
                continue

            valid_state[str(guid)] = datetime_to_string(dt)

        print(
            f"{len(valid_state)} persistente pubDates geladen "
            f"uit {STATE_FILE}."
        )

        return valid_state

    except (json.JSONDecodeError, OSError, ValueError) as error:
        raise RuntimeError(
            f"Statusbestand {STATE_FILE} kon niet veilig worden gelezen: "
            f"{error}"
        ) from error


def save_pubdate_state(state):
    """Schrijf de status atomair weg om een halfgeschreven bestand te voorkomen."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = STATE_FILE.with_suffix(".json.tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        file.write("\n")

    os.replace(temporary_file, STATE_FILE)

    print(
        f"{len(state)} persistente pubDates opgeslagen "
        f"in {STATE_FILE}."
    )


def get_highest_known_pubdate(state):
    """Bepaal de hoogste eerder toegekende pubDate."""
    pubdates = [
        string_to_datetime(value)
        for value in state.values()
    ]

    valid_pubdates = [
        dt for dt in pubdates
        if dt is not None
    ]

    if not valid_pubdates:
        return None

    return max(valid_pubdates)


def get_document_guid(document):
    """
    Gebruik de PID als stabiele GUID.

    Items zonder PID worden overgeslagen, omdat een persistente pubDate
    zonder stabiele identifier niet betrouwbaar kan worden opgeslagen.
    """
    guid = document.get("pid")

    if not guid:
        return None

    return str(guid).strip()


def source_sort_key(item):
    """
    Zorg voor een stabiele verwerkingsvolgorde van nieuwe items.

    De openbaarmakingsdatum is het eerste sorteerveld. De PID en titel
    voorkomen een willekeurige volgorde bij gelijke datums.
    """
    document = item.get("document", {})

    return (
        document.get("openbaarmakingsdatum", ""),
        document.get("pid", ""),
        document.get("titel", ""),
    )


def assign_persistent_pubdates(results, state):
    """
    Geef nieuwe GUID's een unieke, steeds oplopende pubDate.

    Bestaande GUID's behouden precies dezelfde pubDate als tijdens
    eerdere runs.
    """
    highest_known = get_highest_known_pubdate(state)
    now = utc_now_without_microseconds()

    if highest_known is None:
        next_pubdate = now
    else:
        next_pubdate = max(
            now,
            highest_known + timedelta(seconds=1),
        )

    new_items_count = 0

    # Oudste bronitems eerst behandelen. Daardoor krijgt het nieuwste
    # nieuwe item binnen deze run ook de hoogste persistente pubDate.
    for item in sorted(results, key=source_sort_key):
        document = item.get("document", {})
        guid = get_document_guid(document)

        if not guid:
            title = document.get("titel", "Geen titel")
            print(f"Item zonder PID overgeslagen: {title}")
            continue

        if guid in state:
            continue

        state[guid] = datetime_to_string(next_pubdate)

        print(
            f"Nieuwe persistente pubDate: "
            f"{guid} -> {state[guid]}"
        )

        next_pubdate += timedelta(seconds=1)
        new_items_count += 1

    return new_items_count


def create_feed(results, state):
    """Maak de RSS-feed met de persistente pubDates."""
    fg = FeedGenerator()

    fg.id(API_URL)
    fg.title("Open Overheid RSS")
    fg.link(href=API_URL, rel="alternate")
    fg.description("Nieuwe openbaarmakingen")
    fg.language("nl")

    feed_items = []

    for item in results:
        document = item.get("document", {})
        guid = get_document_guid(document)

        if not guid:
            continue

        pubdate = string_to_datetime(state.get(guid))

        if pubdate is None:
            print(f"Geen geldige persistente pubDate voor {guid}.")
            continue

        feed_items.append(
            {
                "document": document,
                "guid": guid,
                "pubdate": pubdate,
            }
        )

    # Hoogste persistente pubDate bovenaan in de RSS-feed.
    feed_items.sort(
        key=lambda item: item["pubdate"],
        reverse=True,
    )

    for item in feed_items:
        document = item["document"]
        guid = item["guid"]
        pubdate = item["pubdate"]

        title = document.get("titel") or "Geen titel"
        url = document.get("pid") or guid
        publisher = document.get("publisher") or ""

        fe = fg.add_entry()

        fe.id(guid)
        fe.title(title)
        fe.link(href=url)
        fe.guid(guid, permalink=True)
        fe.description(publisher)
        fe.pubDate(pubdate)

    fg.rss_file(str(FEED_FILE), pretty=True)

    print(
        f"{FEED_FILE} gemaakt met "
        f"{len(feed_items)} items."
    )


def main():
    response = requests.get(
        API_URL,
        timeout=30,
        headers={
            "User-Agent": "ministerraad-rss-feed/1.0",
            "Accept": "application/json",
        },
    )
    response.raise_for_status()

    data = response.json()
    results = data.get("resultaten", [])

    if not isinstance(results, list):
        raise ValueError(
            "De API-response bevat geen geldige lijst onder 'resultaten'."
        )

    state = load_pubdate_state()

    new_items_count = assign_persistent_pubdates(
        results,
        state,
    )

    # Eerst de toestand bewaren en daarna de feed genereren.
    save_pubdate_state(state)
    create_feed(results, state)

    print(f"Nieuwe RSS-items in deze run: {new_items_count}")


if __name__ == "__main__":
    main()
