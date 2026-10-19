# ============================================
# FILE: radio_stations.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radio stations of each country (radio.py, ROADMAP 2.21): the list of the
country of the place of the weather (config.WEATHER_COUNTRY, settings page
of the TV), else of the language of the Raspberry. config.RADIO_STATIONS
(a list) wins over them: one's own stations.

Each station: name (said and shown on the TV), FM frequency in the biggest
town of the country (Paris, Madrid, London, Lisbon, Mexico City, New York;
only a name, to ask for it: "Robot, radio 105.4") and address of its stream
on the internet. The addresses were checked on a Raspberry Pi on 19/10/2026
with the options of radio.py (http / https only); a stream that stops
working only turns that station off (radio.py, check).

The country is a free text of the settings page ("Espagne", "España",
"Spain", "ES"): compared without accents nor case to the names below, in
French, English, Spanish and Portuguese.
"""

import re
import unicodedata

STREAM_THE_WORLD = "https://playerservices.streamtheworld.com/api/livestream-redirect/"
BBC = "http://as-hls-ww-live.akamaized.net/"

STATIONS = {
    # Paris
    "FR": [
        {"name": "France Inter", "frequency": 87.8, "url": "https://icecast.radiofrance.fr/franceinter-midfi.mp3"},
        {"name": "France Musique", "frequency": 91.7, "url": "https://icecast.radiofrance.fr/francemusique-midfi.mp3"},
        {"name": "France Culture", "frequency": 93.5, "url": "https://icecast.radiofrance.fr/franceculture-midfi.mp3"},
        {"name": "FIP", "frequency": 105.1, "url": "https://icecast.radiofrance.fr/fip-midfi.mp3"},
        {"name": "Franceinfo", "frequency": 105.5, "url": "https://icecast.radiofrance.fr/franceinfo-midfi.mp3"},
        {"name": "RTL", "frequency": 104.3, "url": "http://icecast.rtl.fr/rtl-1-44-128"},
        {"name": "Europe 1", "frequency": 104.7, "url": "https://stream.europe1.fr/europe1.mp3"},
        {"name": "Nostalgie", "frequency": 90.4, "url": "https://streaming.nrjaudio.fm/oug7girb92oc"},
        {"name": "Chérie FM", "frequency": 91.3, "url": "https://cdnradio.streamakaci.com/cheriefm1.mp3"},
        {"name": "NRJ", "frequency": 100.3, "url": "https://scdn.nrjaudio.fm/adwz2/fr/30001/mp3_128.mp3"},
        {"name": "RFM", "frequency": 103.9, "url": "https://rfm.lmn.fm/rfm.mp3"},
        {"name": "Radio Classique", "frequency": 101.1, "url": "http://radioclassique.ice.infomaniak.ch/radioclassique-high.mp3"},
    ],
    # Madrid
    "ES": [
        {"name": "Radio Nacional", "frequency": 88.2, "url": "https://dispatcher.rndfnk.com/crtve/rne1/mad/mp3/high"},
        {"name": "Radio Clásica", "frequency": 96.5, "url": "https://dispatcher.rndfnk.com/crtve/rnerc/main/mp3/high"},
        {"name": "Radio 3", "frequency": 93.2, "url": "https://rtvelivestream.rtve.es/rtvesec/rne/rne_r3_main.m3u8"},
        {"name": "Cadena SER", "frequency": 105.4, "url": STREAM_THE_WORLD + "CADENASER.mp3"},
        {"name": "COPE", "frequency": 106.3, "url": "https://net1-cope-rrcast.flumotion.com/cope/net1.mp3"},
        {"name": "Onda Cero", "frequency": 98.0, "url": "https://atres-live.ondacero.es/live/ondacero/bitrate_1.m3u8"},
        {"name": "esRadio", "frequency": 99.1, "url": "https://livestreaming3.esradio.fm/stream64.mp3"},
        {"name": "Los 40", "frequency": 93.9, "url": STREAM_THE_WORLD + "LOS40.mp3"},
        {"name": "Cadena Dial", "frequency": 91.7, "url": STREAM_THE_WORLD + "CADENADIAL.mp3"},
        {"name": "Cadena 100", "frequency": 99.5, "url": "https://cadena100-streamers-mp3.flumotion.com/cope/cadena100.mp3"},
        {"name": "Europa FM", "frequency": 91.0, "url": "https://atres-live.europafm.com/live/europafm/bitrate_1.m3u8"},
        {"name": "Rock FM", "frequency": 101.7, "url": "http://flucast34-h-cloud.flumotion.com/cope/rockfm-low.mp3"},
    ],
    # London
    "GB": [
        {"name": "BBC Radio 1", "frequency": 98.8,
         "url": BBC + "pool_01505109/live/ww/bbc_radio_one/bbc_radio_one.isml/bbc_radio_one-audio%3d128000.norewind.m3u8"},
        {"name": "BBC Radio 2", "frequency": 89.1,
         "url": BBC + "pool_74208725/live/ww/bbc_radio_two/bbc_radio_two.isml/bbc_radio_two-audio%3d128000.norewind.m3u8"},
        {"name": "BBC Radio 3", "frequency": 91.3,
         "url": BBC + "pool_23461179/live/ww/bbc_radio_three/bbc_radio_three.isml/bbc_radio_three-audio%3d128000.norewind.m3u8"},
        {"name": "BBC Radio 4", "frequency": 93.5,
         "url": BBC + "pool_55057080/live/ww/bbc_radio_fourfm/bbc_radio_fourfm.isml/bbc_radio_fourfm-audio%3d128000.norewind.m3u8"},
        {"name": "BBC Radio London", "frequency": 94.9,
         "url": BBC + "pool_98137350/live/ww/bbc_london/bbc_london.isml/bbc_london-audio%3d128000.norewind.m3u8"},
        {"name": "Classic FM", "frequency": 100.9, "url": "https://media-ssl.musicradio.com/ClassicFMMP3"},
        {"name": "Capital", "frequency": 95.8, "url": "https://media-ssl.musicradio.com/CapitalMP3"},
        {"name": "Heart", "frequency": 106.2, "url": "https://media-ssl.musicradio.com/HeartLondonMP3"},
        {"name": "LBC", "frequency": 97.3, "url": "https://media-ssl.musicradio.com/LBCLondonMP3"},
        {"name": "Smooth", "frequency": 102.2, "url": "https://media-ssl.musicradio.com/SmoothLondonMP3"},
        {"name": "Radio X", "frequency": 104.9, "url": "https://media-ssl.musicradio.com/RadioXLondonMP3"},
        {"name": "Kiss", "frequency": 100.0, "url": "https://live-kiss.sharp-stream.com/kiss100.mp3"},
    ],
    # Lisbon
    "PT": [
        {"name": "Antena 1", "frequency": 95.7, "url": "https://radiocast.rtp.pt/antena180a.mp3"},
        {"name": "Antena 2", "frequency": 94.4, "url": "https://radiocast.rtp.pt/antena280a.mp3"},
        {"name": "Antena 3", "frequency": 100.3, "url": "https://radiocast.rtp.pt/antena380a.mp3"},
        {"name": "TSF", "frequency": 89.5, "url": "https://directo.tsf.pt/tsfdirecto.mp3"},
        {"name": "Renascença", "frequency": 103.4, "url": STREAM_THE_WORLD + "RADIO_RENASCENCA.mp3"},
        {"name": "RFM", "frequency": 93.2, "url": STREAM_THE_WORLD + "RFM.mp3"},
        {"name": "Comercial", "frequency": 97.4, "url": "https://stream-icy.bauermedia.pt/comercial.mp3"},
        {"name": "M80", "frequency": 104.3, "url": "https://stream-icy.bauermedia.pt/m80.mp3"},
        {"name": "Cidade FM", "frequency": 107.2, "url": "https://stream-icy.bauermedia.pt/cidade.mp3"},
        {"name": "Smooth FM", "frequency": 96.6, "url": "https://stream-icy.bauermedia.pt/smooth.aac"},
        {"name": "Mega Hits", "frequency": 92.4, "url": STREAM_THE_WORLD + "MEGA_HITS.mp3"},
        {"name": "Observador", "frequency": 98.7, "url": "http://195.23.85.126:8455/stream"},
    ],
    # Mexico City
    "MX": [
        {"name": "W Radio", "frequency": 96.9, "url": STREAM_THE_WORLD + "W_RADIOAAC.aac"},
        {"name": "Radio Fórmula", "frequency": 104.1, "url": "https://mdstrm.com/audio/61e1dfd2658baf082814e25d/live.m3u8"},
        {"name": "MVS Noticias", "frequency": 102.5, "url": STREAM_THE_WORLD + "XHMVSFM_SC"},
        {"name": "Los 40", "frequency": 101.7, "url": STREAM_THE_WORLD + "LOS40_MEXICOAAC.aac"},
        {"name": "Exa FM", "frequency": 104.9, "url": STREAM_THE_WORLD + "XHEXA_SC"},
        {"name": "Mix", "frequency": 106.5, "url": STREAM_THE_WORLD + "XHDFMFMAAC.aac"},
        {"name": "Ke Buena", "frequency": 92.9, "url": STREAM_THE_WORLD + "KEBUENAAAC.aac"},
        {"name": "Amor", "frequency": 95.3, "url": STREAM_THE_WORLD + "XHSHFMAAC.aac"},
        {"name": "Alfa", "frequency": 91.3, "url": STREAM_THE_WORLD + "XHFAJ_FMAAC.aac"},
        {"name": "La Z", "frequency": 107.3, "url": STREAM_THE_WORLD + "XEQR_FMAAC.aac"},
        {"name": "Joya", "frequency": 93.7, "url": STREAM_THE_WORLD + "XEJP_FMAAC.aac"},
        {"name": "Stereo Cien", "frequency": 100.1, "url": STREAM_THE_WORLD + "XHMMFMAAC.aac"},
    ],
    # New York
    "US": [
        {"name": "WNYC", "frequency": 93.9, "url": "https://fm939.wnyc.org/wnycfm-web"},
        {"name": "WQXR", "frequency": 105.9, "url": "https://stream.wqxr.org/wqxr-web"},
        {"name": "WFUV", "frequency": 90.7, "url": "https://onair.wfuv.org/onair-hi"},
        {"name": "WBGO", "frequency": 88.3, "url": "https://ais-sa8.cdnstream1.com/3629_128.mp3"},
        {"name": "Z100", "frequency": 100.3, "url": "https://stream.revma.ihrhls.com/zc1469"},
        {"name": "Lite FM", "frequency": 106.7, "url": "https://stream.revma.ihrhls.com/zc1477"},
        {"name": "Q104", "frequency": 104.3, "url": "https://stream.revma.ihrhls.com/zc1465"},
        {"name": "Power 105", "frequency": 105.1, "url": "https://stream.revma.ihrhls.com/zc1481"},
        {"name": "KTU", "frequency": 103.5, "url": "https://stream.revma.ihrhls.com/zc1473"},
        {"name": "Hot 97", "frequency": 97.1, "url": STREAM_THE_WORLD + "WQHTFMAAC.aac"},
    ],
}

# Names of the countries (without accents, small letters; fr, en, es, pt)
COUNTRY_NAMES = {
    "FR": ("france", "francia", "franca", "fr"),
    "ES": ("espagne", "espana", "spain", "espanha", "es"),
    "GB": ("angleterre", "royaume uni", "grande bretagne", "ecosse", "pays de galles", "england", "united kingdom",
           "great britain", "scotland", "wales", "uk", "gb", "inglaterra", "reino unido", "gran bretana", "escocia",
           "gales", "gra bretanha"),
    "PT": ("portugal", "pt"),
    "MX": ("mexique", "mexico", "mx"),
    "US": ("etats unis", "etats unis d amerique", "usa", "us", "united states", "united states of america",
           "america", "estados unidos", "estados unidos de america", "eeuu", "eua"),
}
# Country not known: the stations of the language of the Raspberry
LANGUAGE_COUNTRIES = {"fr": "FR", "en": "GB", "es": "ES"}


def simple(text):
    """"États-Unis" -> "etats unis" (no accents, small letters, words only)."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def country_code(country):
    """Code of a country written on the settings page ("Espagne" -> "ES"), or None."""
    name = simple(country)
    return next((code for code, names in COUNTRY_NAMES.items() if name in names), None)


def stations_for(country, language):
    """Stations of the country (else of the language, else of France): new dicts each time."""
    code = country_code(country) or LANGUAGE_COUNTRIES.get(language) or "FR"
    return [dict(station) for station in STATIONS[code]]
