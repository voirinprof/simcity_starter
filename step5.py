"""
Étape 5 — Isoler les points LiDAR qui correspondent à la végétation.

On garde les points "non classés" du LiDAR, puis on retire ceux
qui tombent sur les bâtiments ou sur les routes. Ce qui reste est
principalement de la végétation haute (arbres).

Données : LiDAR issu d'une source ouverte ; bâtiments et routes
(ex. OpenStreetMap, ODbL). Vérifier la licence de chaque source.
"""

from pathlib import Path

import laspy
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from shapely import contains_xy, union_all

# Paramètres
LAZ = "data/processed/lidar/points_zone.laz"
BATIMENTS = "data/raw/local/buildings.geojson"
ROUTES = "data/raw/local/roads.geojson"
SORTIE = "data/processed/lidar/points_vegetation.laz"

# Largeur des zones d'exclusion autour des objets (en mètres).
# Une route est une ligne : il faut l'élargir pour couvrir la chaussée.
BUFFER_ROUTE = 4.0
BUFFER_BATIMENT = 1.0

# 1. Lire le nuage LiDAR
las = laspy.read(LAZ)
crs = las.header.parse_crs()
if crs is None:
    raise ValueError("CRS du LiDAR absent")

# 2. Conserver uniquement les points Unclassified
# Classes LiDAR standard (ASPRS) : 1 = non classé, 2 = sol,
# 6 = bâtiment, 9 = eau… Selon le fournisseur, la végétation
# se retrouve souvent dans la classe 1.
classe = np.asarray(las.classification)
selection = classe == 1   # Masque booléen : True pour les points gardés

x = np.asarray(las.x)[selection]
y = np.asarray(las.y)[selection]
z = np.asarray(las.z)[selection]

print(f"Points initiaux : {len(las.points):,}")
print(f"Points Unclassified : {len(x):,}")

# 3. Lire les couches vectorielles
# Toujours dans le même CRS que le LiDAR pour pouvoir les comparer.
batiments = gpd.read_file(BATIMENTS).to_crs(crs)
routes = gpd.read_file(ROUTES).to_crs(crs)

# 4. Construire les masques
# On élargit chaque objet (buffer), puis on fusionne tout en une seule
# géométrie (union_all) : le test "point dans polygone" est alors fait une fois.
emprises_batiments = union_all(
    batiments.geometry.buffer(BUFFER_BATIMENT)
)

emprises_routes = union_all(
    routes.geometry.buffer(BUFFER_ROUTE)
)

# 5. Identifier les points masqués
sur_batiment = contains_xy(emprises_batiments, x, y)
sur_route = contains_xy(emprises_routes, x, y)

# 6. Conserver les points hors des masques
# | = "ou" logique, ~ = "non" logique, élément par élément
conserver = ~(sur_batiment | sur_route)

print(f"Points après masquage : {conserver.sum():,}")

# 7. Exporter les points LAS complets
# On retrouve les indices des points conservés dans le nuage d'origine,
# pour copier tous leurs attributs (intensité, classe, retours…).
indices = np.flatnonzero(selection)        # Indices des points de classe 1
indices_conserves = indices[conserver]     # … qui sont hors des masques

# Nouveau fichier avec le même en-tête (CRS, échelle, format)
las_filtre = laspy.LasData(las.header.copy())
las_filtre.points = las.points[indices_conserves]

Path(SORTIE).parent.mkdir(parents=True, exist_ok=True)
las_filtre.write(SORTIE)

print(f"Fichier enregistré : {SORTIE}")

# 8. Visualisation
# Vue de dessus, couleur = altitude des points
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

axes[0].scatter(x, y, c=z, s=0.3, cmap="terrain")
axes[0].set_title("Points Unclassified")

axes[1].scatter(
    x[conserver], y[conserver],
    c=z[conserver], s=0.3, cmap="terrain"
)
axes[1].set_title("Après masquage bâtiments + routes")

for ax in axes:
    ax.set_aspect("equal")
    ax.axis("off")

plt.tight_layout()
plt.savefig("lidar_unclassified_masque.png", dpi=180)
plt.close()
