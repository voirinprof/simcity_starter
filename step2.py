"""
Étape 2 — Comparer deux sources de bâtiments.

On met côte à côte les bâtiments d'OpenStreetMap et ceux du
Référentiel bâtiment du Québec pour le même quartier, afin de
juger de la complétude de chaque source.

Données : © les contributeurs d'OpenStreetMap (ODbL) ;
Référentiel bâtiment — Données Québec (vérifier la licence).
"""

import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point

# Notre quartier
LAT, LON = 45.4042, -71.8929
COTE = 500
FICHIER = "data/sources/Referentiel_batiment.gpkg"

# Carré de 500 m en UTM
# Même principe qu'à l'étape 1 : on passe en mètres (EPSG:32619)
# pour construire un carré de 500 m de côté.
centre = gpd.GeoSeries(
    [Point(LON, LAT)], crs=4326
).to_crs(32619)

zone = centre.iloc[0].buffer(COTE / 2, cap_style=3)

# Bâtiments OpenStreetMap
# Requête en degrés (EPSG:4326), résultat ramené en mètres.
osm = ox.features_from_polygon(
    gpd.GeoSeries([zone], crs=32619).to_crs(4326).iloc[0],
    {"building": True}
).to_crs(32619)

# Certains bâtiments OSM sont de simples points : on ne garde que
# les surfaces, puis on coupe sur le carré d'étude.
osm = osm[osm.geometry.type.isin(["Polygon", "MultiPolygon"])]
osm = osm.clip(zone)

# Bâtiments du Québec : extrait spatial seulement
# Le fichier couvre toute la province : on ne lit que le rectangle
# englobant (bbox) de notre zone. La bbox doit être exprimée dans
# le CRS du fichier ; on lit donc une seule ligne (rows=1) pour le connaître.
quebec = gpd.read_file(
    FICHIER,
    bbox=tuple(
    gpd.GeoSeries([zone], crs=32619)
    .to_crs(gpd.read_file(FICHIER, rows=1).crs)
    .total_bounds  # (xmin, ymin, xmax, ymax)
)
).to_crs(32619).clip(zone)

# Comparaison côte à côte
fig, axes = plt.subplots(1, 2, figsize=(12, 6))

for ax, data, titre, couleur in [
    (axes[0], osm, "OpenStreetMap", "#d97757"),
    (axes[1], quebec, "Référentiel du Québec", "#377eb8"),
]:
    if not data.empty:
        data.plot(ax=ax, color=couleur, edgecolor="black")
    # Même cadrage pour les deux cartes, pour comparer à l'œil
    ax.set_xlim(zone.bounds[0], zone.bounds[2])
    ax.set_ylim(zone.bounds[1], zone.bounds[3])
    ax.set_aspect("equal")
    ax.set_title(f"{titre} — {len(data)} objets")
    ax.axis("off")

plt.tight_layout()
plt.savefig("comparaison_batiments.png", dpi=180)
#plt.show()
