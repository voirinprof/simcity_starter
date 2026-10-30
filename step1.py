"""
Étape 1 — Délimiter un quartier et interroger OpenStreetMap.

On part d'un point GPS, on trace un carré de 500 m autour,
puis on télécharge les objets OpenStreetMap (bâtiments, routes,
parcs, stationnements) qui s'y trouvent et on les affiche.

Données : © les contributeurs d'OpenStreetMap (licence ODbL).
"""

import osmnx as ox                # Accès simplifié à l'API OpenStreetMap
import geopandas as gpd           # Tableaux de données avec géométries
import matplotlib.pyplot as plt   # Affichage de cartes et graphiques
from shapely.geometry import Point

# Paramètres de la démonstration : Sherbrooke
LATITUDE = 45.4042
LONGITUDE = -71.8929
COTE = 500  # mètres

# 1. Passer des degrés aux mètres (UTM 19N)
# EPSG:4326 = coordonnées GPS en degrés (longitude, latitude).
# EPSG:32619 = UTM zone 19 Nord, un système en mètres adapté au sud du Québec.
# On reprojette car un "buffer" de 250 n'a de sens qu'en mètres.
centre = gpd.GeoSeries(
    [Point(LONGITUDE, LATITUDE)], crs="EPSG:4326"  # Attention : (x=lon, y=lat)
).to_crs("EPSG:32619")

# 2. Construire le carré autour du point
x, y = centre.iloc[0].x, centre.iloc[0].y
# buffer(COTE / 2) crée une zone de 250 m autour du point ;
# cap_style=3 donne des coins carrés au lieu d'un cercle.
zone = gpd.GeoSeries.from_wkt(
    [Point(x, y).buffer(COTE / 2, cap_style=3).wkt],
    crs=centre.crs
)

# 3. Interroger OpenStreetMap
# Dans OSM, chaque objet est décrit par des "tags" (clé = valeur).
# True = toutes les valeurs de la clé ; une liste = seulement ces valeurs.
tags = {
    "building": True,
    "highway": True,
    "leisure": ["park", "garden"],
    "amenity": ["parking"],
}

# OSMnx attend un polygone en degrés : on repasse donc en EPSG:4326
# pour la requête, puis on ramène le résultat en mètres (UTM).
objets = ox.features_from_polygon(
    zone.to_crs("EPSG:4326").iloc[0], tags
).to_crs(centre.crs)

# 4. Séparer les catégories
# Chaque tag devient une colonne : un objet appartient à une catégorie
# si la colonne correspondante est renseignée (notna).
batiments = objets[objets["building"].notna()]
routes = objets[objets["highway"].notna()]
parcs = objets[objets["leisure"].notna()]
parkings = objets[objets["amenity"] == "parking"]

# 5. Afficher le quartier
fig, ax = plt.subplots(figsize=(9, 9))

# L'ordre compte : les couches dessinées en dernier passent au-dessus.
for couche, couleur, nom in [
    (parcs, "#9ccc65", "Parcs"),
    (parkings, "#c5c5c5", "Stationnements"),
    (routes, "#f5a623", "Routes"),
    (batiments, "#c75b4b", "Bâtiments"),
]:
    if not couche.empty:
        # clip() coupe les objets qui dépassent du carré d'étude.
        couche.clip(zone.iloc[0]).plot(
            ax=ax, color=couleur, label=nom
        )

# Contour du carré et cadrage de la carte sur la zone
zone.boundary.plot(ax=ax, color="black", linewidth=2)
ax.set_xlim(x - COTE / 2, x + COTE / 2)
ax.set_ylim(y - COTE / 2, y + COTE / 2)
ax.set_aspect("equal")  # 1 m en x = 1 m en y (pas de déformation)
ax.set_title("Un quartier de 500 × 500 m — OpenStreetMap")
plt.tight_layout()
plt.savefig("quartier_osm.png", dpi=180)
#plt.show()

# 6. (Optionnel) Exporter les couches OSM en GeoJSON
# Décommentez ce bloc pour enregistrer chaque catégorie dans un fichier.
# Les noms buildings.geojson et roads.geojson sont ceux attendus
# par les étapes 4 et 5.
# On ne garde que quelques colonnes : les objets OSM ont des dizaines
# d'attributs, souvent vides. On exporte en EPSG:4326, le système
# recommandé par la norme GeoJSON.
# Rappel : ces données restent sous licence ODbL
# (attribution « © les contributeurs d'OpenStreetMap »).
#
# from pathlib import Path
#
# DOSSIER = Path("data/raw/local")
# DOSSIER.mkdir(parents=True, exist_ok=True)
#
# for couche, nom, colonne in [
#     (batiments, "buildings", "building"),
#     (routes, "roads", "highway"),
#     (parcs, "parks", "leisure"),
#     (parkings, "parkings", "amenity"),
# ]:
#     if couche.empty:
#         continue
#
#     # Colonnes conservées : le nom (s'il existe), le tag OSM et la géométrie
#     colonnes = [c for c in ["name", colonne] if c in couche.columns]
#
#     extrait = couche[colonnes + ["geometry"]].clip(zone.iloc[0])
#     extrait.to_crs("EPSG:4326").to_file(
#         DOSSIER / f"{nom}.geojson", driver="GeoJSON"
#     )
#
#     print(f"{nom}: {len(extrait)} objets exportés")
