# app.py
import streamlit as st
import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
from io import BytesIO
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Generator - SBB Zugsbenützungsrapport", 
    layout="wide", 
    page_icon=":material/subway_walk:",
    menu_items={
        'About': """
            **Automatischer Zugsbenützungsrapport — Schweizer Armee**  

            **Version:** 1.0.0  
            **Entwickelt von:** Nico Fehr

            Diese Anwendung dient der **Unterstützung bei der Erstellung des SBB-Zugsbenützungsrapports Form 7.26**.  
            Sie hilft dabei, Excel-Dateien mit anonymisierten Daten der Armee zu verarbeiten und die Summen für 1. und 2. Klasse sowie die Zuordnung zu Bahnhöfen automatisch zu berechnen.  

            **Hinweis:**  
            - Die App speichert keine Daten dauerhaft.  
            - Es dürfen keine personenbezogenen Daten hochgeladen werden.  
            - Für die Richtigkeit der Ergebnisse übernimmt der Entwickler keine Haftung.  
        """
    }
)

with st.sidebar:
    st.image("assets/logo.gif", width='stretch')
    st.markdown("### Automatischer SBB Zugsbenützungsrapport")
    st.markdown(
    "Diese Applikation hilft bei der Erstellung des Zugsbenützungsrapport (Form 7.26 - Meldung über Militär-, Urlauber- und Entlassungstransporte) "
    "wie im Reglement 51.024 (Ziffer 166-167 ODA) erwähnt."
    )
    st.markdown("**Version:** 1.0.0  \n**Entwickelt von:** Nico Fehr")
    st.markdown("**Website:** [nicofehr.dev](https://nicofehr.dev)")

st.title("Automatischer Zugsbenützungsrapport für die Schweizer Armee")

st.markdown(
    "Lade eine Excel-Datei mit Spalten **Grad**, **Wohnort**, **Postleitzahl** hoch. "
    "Die App bestimmt den nächstgelegenen Bahnhof (aus einer vordefinierten Liste) "
    "und erstellt Summen für 1. / 2. Klasse."
)

# --- Datenschutz & Haftung im separaten Panel ---
with st.expander("🛡 Datenschutzhinweis & Haftungsausschluss"):
    st.markdown("""
    Diese Anwendung wird bereitgestellt von **Nico Fehr** und dient ausschliesslich der technischen Unterstützung bei der Erstellung des **SBB-Zugsbenützungsrapports für die Schweizer Armee**.  
    
    Es dürfen **keine personenbezogenen Daten** (z. B. Namen, Adressen, Telefonnummern, AHV-Nummern oder dienstliche Kennungen) hochgeladen oder verarbeitet werden.  
    Die hochgeladenen Excel-Dateien sollen **ausschliesslich anonymisierte oder aggregierte Informationen** enthalten, wie beispielsweise **Grad**, **Wohnort** und **Postleitzahl**.  
    
    Die Verarbeitung der Daten erfolgt **ausschliesslich lokal im Arbeitsspeicher während der Nutzung** der Anwendung.  
    **Es werden keine Daten dauerhaft gespeichert, übertragen oder weitergegeben.**
    
    Der Anbieter dieser Anwendung übernimmt **keine Haftung** für:
    - die Korrektheit oder Vollständigkeit der erzeugten Ergebnisse,  
    - die rechtmässige Nutzung der Anwendung oder der hochgeladenen Daten,  
    - sowie für Schäden oder Ansprüche, die aus der Verwendung der App entstehen.  
    
    Mit der Nutzung der Anwendung erklären Sie sich mit diesen Bedingungen einverstanden.
    """)

# --- Konfiguration: Bahnhofliste mit groben Koordinaten (kann angepasst werden) ---
STATIONS = {
    "Aarau": (47.3919252, 8.0511985),
    "Basel SBB": (47.5476225, 7.5896417),
    "Bellinzona": (46.1951237, 9.0290235),
    "Bern": (46.9469020, 7.4408922),
    "Biel/Bienne": (47.1320700, 7.2456600),
    "Brig": (46.3191856, 7.9882631),
    "Chur": (46.8531182, 9.5301857),
    "Fribourg": (46.8029610, 7.1510169),
    "Genf": (46.2102288, 6.1426218),
    "Lausanne": (46.5170017, 6.6291687),
    "Luzern": (47.0510534, 8.3103560),
    "Olten": (47.3525166, 7.9070235),
    "Schaffhausen": (47.6993065, 8.6337403),
    "Sion": (46.2274616, 7.3593303),
    "St. Gallen": (47.4229423, 9.3700315),
    "Thun": (46.7551576, 7.6298577),
    "Winterthur": (47.5003138, 8.7239736),
    "Zürich": (47.3781008, 8.5393635),
}
STATION_NAMES = list(STATIONS.keys())

# Ranks that travel 2nd class
CLASS2_RANKS = {"Rekr", "Sdt", "Gfr", "Obgfr", "Wm", "Obwm"}

# --- Helpers ---
def haversine(lat1, lon1, lat2, lon2):
    """Haversine distance in kilometers"""
    # convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    km = 6371.0 * c
    return km

def get_location_by_plz(query, user_agent):
    url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
    print(url)
    
    try:
        result = requests.get(url=url, headers={ "User-Agent": user_agent }, verify=False)
        result_json = result.json()
        return (float(result_json[0]["lat"]), float(result_json[0]["lon"]))
    except:
        return None

@st.cache_data(show_spinner=False)
def geocode_postal_codes(plz_list, user_agent="sbb_rapport_app"):
    """Geocode postal codes (list). Returns dict plz -> (lat, lon) or None."""
    results = {}
    for plz in plz_list:
        if pd.isna(plz):
            results[plz] = None
            continue
        # Some PLZ inputs might be numeric; make string and append 'Switzerland' for better results
        query = f"{str(int(plz))}, Switzerland" if isinstance(plz, (int, np.integer)) or (isinstance(plz, str) and str(plz).isdigit()) else f"{plz}, Switzerland"
        try:
            loc = get_location_by_plz(query=query, user_agent=user_agent)
            if loc:
                results[plz] = loc
            else:
                results[plz] = None
        except Exception as e:
            results[plz] = None
    return results

def find_nearest_station(lat, lon):
    best = None
    best_dist = float("inf")
    for name, (s_lat, s_lon) in STATIONS.items():
        d = haversine(lat, lon, s_lat, s_lon)
        if d < best_dist:
            best = name
            best_dist = d
    return best, best_dist

def to_excel_bytes(df_dict):
    """df_dict: dict of sheet_name -> DataFrame"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in df_dict.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        writer.close()
    return output.getvalue()

# --- UI: Upload ---
uploaded_file = st.file_uploader("Excel-Datei hochladen (xlsx)", type=["xlsx", "xls"])
sample_btn = st.button("Beispiel-Excel herunterladen")
if sample_btn:
    sample = pd.DataFrame({
        "Grad": ["Rekr", "Oberst", "Sdt", "Gfr"],
        "Wohnort": ["Zürich", "Bern", "Lausanne", "Lugano"],
        "Postleitzahl": [8001, 3000, 1003, 6900]
    })
    b = to_excel_bytes({"input_sample": sample})
    st.download_button("Download Beispiel", data=b, file_name="sbb_rapport_sample.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if uploaded_file is None:
    st.info("Lade eine Excel-Datei hoch, um die Auswertung zu starten. Alternativ lade die Beispieldatei herunter und teste mit ihr.")
    st.stop()



# --- Verarbeitung ---
try:
    df_input = pd.read_excel(uploaded_file, engine="openpyxl")
except Exception as e:
    st.error(f"Fehler beim Einlesen der Excel-Datei: {e}")
    st.stop()

# Check required columns
required = {"Grad", "Wohnort", "Postleitzahl"}
if not required.issubset(set(df_input.columns)):
    st.error(f"Die Excel-Datei muss die Spalten {required} enthalten. Gefundene Spalten: {list(df_input.columns)}")
    st.stop()

st.write("Eingelesene Daten (erste 20 Zeilen):")
st.dataframe(df_input.head(20))

# Prepare PLZ list to geocode (unique)
plz_values = df_input["Postleitzahl"].dropna().unique().tolist()
with st.spinner("Geokodiere Postleitzahlen (externer Dienst)..."):
    plz_to_coords = geocode_postal_codes(plz_values)

# Map coordinates into dataframe
latitudes = []
longitudes = []
geocode_failed = 0
for plz in df_input["Postleitzahl"]:
    coords = plz_to_coords.get(plz)
    if coords:
        latitudes.append(coords[0])
        longitudes.append(coords[1])
    else:
        latitudes.append(np.nan)
        longitudes.append(np.nan)
        geocode_failed += 1

df_input = df_input.copy()
df_input["lat"] = latitudes
df_input["lon"] = longitudes

# For rows with missing geocode, allow user to manually enter or leave as NaN
if geocode_failed > 0:
    st.warning(f"Für {geocode_failed} PLZ(s) konnte keine Geokodierung gefunden werden. Du kannst diese später manuell ergänzen oder die PLZ prüfen.")
    st.caption("Tipp: Formate wie '8001' oder '3000' funktionieren meist; bei 'S-8001' o.ä. kann es Probleme geben.")

# Find nearest station when coords available
nearest_station = []
distance_km = []
for lat, lon in zip(df_input["lat"], df_input["lon"]):
    if pd.notna(lat) and pd.notna(lon):
        s, d = find_nearest_station(lat, lon)
        nearest_station.append(s)
        distance_km.append(round(d, 2))
    else:
        nearest_station.append(None)
        distance_km.append(None)

df_input["Nächster Bahnhof"] = nearest_station
df_input["Distanz_km"] = distance_km

# Determine travel class
def classify(grad):
    try:
        if str(grad).strip() in CLASS2_RANKS:
            return "2. Klasse"
        else:
            return "1. Klasse"
    except:
        return "1. Klasse"

df_input["Klasse"] = df_input["Grad"].apply(classify)

# Aggregationen
total_by_class = df_input["Klasse"].value_counts().reindex(["1. Klasse", "2. Klasse"]).fillna(0).astype(int)
st.subheader("Totals nach Klasse")
st.table(total_by_class.rename_axis("Klasse").reset_index().rename(columns={"index":"Klasse", "Klasse":"Anzahl"}))


st.subheader("Summen pro Bahnhof (nur für zugeordnete)")
per_station = df_input.dropna(subset=["Nächster Bahnhof"]).groupby("Nächster Bahnhof").agg(
    Anzahl=("Nächster Bahnhof", "count"),
    Anzahl_1Kl=("Klasse", lambda s: (s=="1. Klasse").sum()),
    Anzahl_2Kl=("Klasse", lambda s: (s=="2. Klasse").sum())
).reindex(STATION_NAMES).fillna(0).astype(int)
st.dataframe(per_station)

# The SBB question: "Bitte geben Sie an, in welche Regionen die Angehörigen der Armee reisen"
# -> we'll present the sums by Bahnhof as "Region" and allow the user to download or provide a mapping file for custom regions.
st.markdown("**Antwort an SBB:** Summen nach Zielbahnhof (kann als 'Region' verwendet werden).")

# Allow user to download detailed results
st.subheader("Detailtabelle & Download")
st.dataframe(df_input)

# Karte zentrieren auf Schweiz
m = folium.Map(location=[46.8, 8.2], zoom_start=7)

# Marker für jeden Bahnhof
for i, row in df_input.iterrows():
    html = f"""
        <div style="min-width: 300px;">
            <h4>{row['Wohnort']}</h4>
            <table style="width:100%"> 
                <tr>
                    <td>Nächster Bahnhof</td>
                    <td>{row['Nächster Bahnhof']}</td>
                </tr>
                <tr>
                    <td>Klasse</td>
                    <td>{row['Klasse']}</td>
                </tr>
                <tr>
                    <td>Distanz</td>
                    <td>{row['Distanz_km']} km</td>
                </tr>
            </table>
        </div>
    """
    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=html,
        icon=folium.Icon(color="green", icon="train", prefix="fa")
    ).add_to(m)

# Karte in Streamlit anzeigen
st_folium(m, width=700, height=500)


# Prepare downloads: detailed + per_station summary
df_station_out = per_station.reset_index().rename(columns={"Nächster Bahnhof":"Bahnhof"})
excel_bytes = to_excel_bytes({
    "detailliert": df_input,
    "pro_bahnhof": df_station_out
})
st.download_button("Download Excel: Ergebnis", data=excel_bytes,
                   file_name="sbb_rapport_ergebnis.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# CSV download for SBB form (totals per station)
csv_buf = df_station_out.to_csv(index=False).encode("utf-8")
st.download_button("CSV: Summen pro Bahnhof", data=csv_buf, file_name="sbb_summen_bahnhof.csv", mime="text/csv")

# Optional: allow manual corrections for rows with missing station
st.subheader("Manuelle Korrekturen (optional)")
missing_idx = df_input[df_input["Nächster Bahnhof"].isna()].index.tolist()
if missing_idx:
    st.info(f"{len(missing_idx)} Datensätze ohne zugeordneten Bahnhof. Du kannst diese manuell bearbeiten.")
    edited = df_input.loc[missing_idx, ["Grad", "Wohnort", "Postleitzahl", "lat", "lon"]].copy()
    edited["Nächster Bahnhof (manuell)"] = ""
    st.write("Bearbeite die Felder in der Tabelle und kopiere die gewünschte Bahnhofbezeichnung (z.B. 'Bern', 'Zürich').")
    st.dataframe(edited)
else:
    st.write("Keine manuellen Korrekturen nötig.")

st.markdown("---")
st.markdown("**Erläuterungen & Hinweise**")
st.markdown("""
- Die Geokodierung erfolgt über einen externen Dienst (Nominatim).
- Mil. Grade 2. Klasse: Rekr, Sdt, Gfr, Obgfr, Wm, Obwm. Alle anderen Grade werden als 1. Klasse gezählt.
""")


