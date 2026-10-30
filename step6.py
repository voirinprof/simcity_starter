"""
Étape 6 — Détecter les arbres et leurs couronnes.

À partir des points de végétation (étape 5) :
  1. on calcule la hauteur des points au-dessus du sol ;
  2. on retire le bruit avec DBSCAN ;
  3. on construit un modèle de hauteur de canopée (CHM) ;
  4. on repère les sommets (un sommet ≈ un arbre) ;
  5. on délimite chaque couronne par "ligne de partage des eaux".

Données : LiDAR et MNT issus d'une source ouverte
(vérifier la licence du fournisseur).
"""

from pathlib import Path

import laspy
import numpy as np
import geopandas as gpd
import rasterio

from sklearn.cluster import DBSCAN                    # Regroupement par densité
from scipy.ndimage import gaussian_filter, binary_closing
from skimage.feature import peak_local_max            # Détection de maxima locaux
from skimage.segmentation import watershed            # Ligne de partage des eaux
from rasterio.features import shapes                  # Raster → polygones
from rasterio.transform import from_origin
from rasterio.warp import transform as transformer
from shapely.geometry import shape, Point
from shapely.ops import unary_union

# Paramètres
LAZ = "data/processed/lidar/points_vegetation.laz"
MNT = "data/processed/lidar/mnt_clipped.tif"
SORTIE = "data/processed/lidar/couronnes.gpkg"

HAUTEUR_MIN = 2.5    # Hauteur minimale d'un arbre (m)
RESOLUTION = 0.5     # Taille d'un pixel du CHM (m)
DISTANCE_MIN = 3.0   # Distance minimale entre deux sommets d'arbres (m)
SURFACE_MIN = 4.0    # Surface minimale d'une couronne (m²)

# Paramètres DBSCAN
EPS = 1.0         # Rayon de voisinage (m)
MIN_POINTS = 5    # Nombre minimal de voisins pour ne pas être du "bruit"

# 1. Lire le LiDAR
las = laspy.read(LAZ)
crs = las.header.parse_crs()

if crs is None:
    raise ValueError("CRS du LiDAR absent")

x = np.asarray(las.x)
y = np.asarray(las.y)
z = np.asarray(las.z)

print(f"Points LiDAR : {len(x):,}")

# 2. Normaliser les hauteurs avec le MNT
# Même principe qu'à l'étape 4 : hauteur = altitude du point - altitude du sol.
with rasterio.open(MNT) as src:
    if src.crs is None:
        raise ValueError("CRS du MNT absent")

    if src.crs != crs:
        mx, my = transformer(crs, src.crs, x, y)
    else:
        mx, my = x, y

    valeurs = np.ma.array([
        v[0] for v in src.sample(zip(mx, my), masked=True)
    ]).filled(np.nan)

h = z - valeurs

# Conserver uniquement les points suffisamment hauts
valides = np.isfinite(h) & (h > HAUTEUR_MIN)
x, y, h = x[valides], y[valides], h[valides]

if len(x) == 0:
    raise ValueError("Aucun point au-dessus du seuil")

print(f"Points après filtrage hauteur : {len(x):,}")

# 3. DBSCAN : éliminer les points isolés
# DBSCAN forme des groupes de points proches en 3D (x, y, h).
# Un point sans assez de voisins reçoit l'étiquette -1 : c'est du bruit
# (fil électrique, oiseau, erreur de mesure…).
coordonnees = np.column_stack((x, y, h))

labels = DBSCAN(
    eps=EPS,
    min_samples=MIN_POINTS,
    n_jobs=-1   # Utilise tous les cœurs du processeur
).fit_predict(coordonnees)

garder = labels != -1

print(f"Points isolés éliminés : {(~garder).sum():,}")

x, y, h = x[garder], y[garder], h[garder]

if len(x) == 0:
    raise ValueError("Aucun point après DBSCAN")

# 4. Construire le CHM
# Le CHM (Canopy Height Model) est une image où chaque pixel
# contient la hauteur du point le plus haut qui y tombe.
# Origine de l'image : coin haut-gauche (xmin, ymax).
xmin, ymax = x.min(), y.max()

# Conversion des coordonnées en indices de colonne et de ligne.
# Les lignes augmentent vers le bas, d'où (ymax - y).
cols = ((x - xmin) / RESOLUTION).astype(int)
rows = ((ymax - y) / RESOLUTION).astype(int)

chm = np.zeros(
    (rows.max() + 1, cols.max() + 1),
    dtype=np.float32
)

# Pour chaque pixel, on garde la hauteur maximale des points qu'il contient.
np.maximum.at(chm, (rows, cols), h)

# 5. Lisser et détecter les sommets
# Masque des pixels "occupés" par de la végétation ; la fermeture
# morphologique bouche les petits trous entre les points.
occupation = binary_closing(
    chm > HAUTEUR_MIN,
    iterations=2
)

# Le lissage évite de détecter plusieurs sommets sur une même couronne.
chm_lisse = gaussian_filter(chm, sigma=1.5)

# Un sommet = pixel plus haut que ses voisins dans un rayon donné.
# min_distance est exprimée en pixels, d'où la division par la résolution.
sommets = peak_local_max(
    chm_lisse,
    min_distance=max(1, int(DISTANCE_MIN / RESOLUTION)),
    threshold_abs=HAUTEUR_MIN,
    labels=occupation.astype(np.uint8)
)

print(f"Sommets détectés : {len(sommets)}")

# Image de "marqueurs" : chaque sommet reçoit un numéro unique (1, 2, 3…)
marqueurs = np.zeros(chm.shape, dtype=np.int32)

for i, (ligne, col) in enumerate(sommets, start=1):
    marqueurs[ligne, col] = i

# 6. Séparer les couronnes
# La ligne de partage des eaux "remplit" des bassins à partir des
# marqueurs. On inverse le CHM (-chm) pour que les sommets des arbres
# deviennent des creux : chaque bassin correspond alors à une couronne.
segments = watershed(
    -chm_lisse,
    marqueurs,
    mask=occupation
)

# 7. Convertir les segments en polygones
# Transformation affine : passage des pixels (ligne, colonne) aux mètres.
transfo = from_origin(xmin, ymax, RESOLUTION, RESOLUTION)

# Regrouper les polygones portant le même identifiant
groupes = {}

# shapes() renvoie un polygone pour chaque zone de pixels de même valeur.
for geom, identifiant in shapes(
    segments.astype("int32"),
    mask=segments > 0,
    transform=transfo
):
    identifiant = int(identifiant)
    groupes.setdefault(identifiant, []).append(shape(geom))

couronnes = []
arbres = []

for identifiant, geometries in groupes.items():
    polygone = unary_union(geometries)
    surface = polygone.area

    # Les toutes petites couronnes sont probablement du bruit
    if surface < SURFACE_MIN:
        continue

    # Position du sommet en mètres (centre du pixel : +0.5)
    ligne, col = sommets[identifiant - 1]
    px, py = transfo * (col + 0.5, ligne + 0.5)

    # Hauteur = pixel le plus haut de la couronne ;
    # rayon = celui d'un cercle de même surface.
    hauteur = float(chm[segments == identifiant].max())
    rayon = float(np.sqrt(surface / np.pi))

    attributs = {
        "arbre_id": identifiant,
        "hauteur_m": round(hauteur, 2),
        "surface_m2": round(surface, 2),
        "diam_m": round(2. * rayon, 2)
    }

    # Deux représentations du même arbre : sa couronne (polygone)
    # et son sommet (point), plus simple à afficher en 3D.
    couronnes.append({
        **attributs,
        "geometry": polygone
    })

    arbres.append({
        **attributs,
        "geometry": Point(px, py)
    })

# 8. Exporter les deux couches
if not arbres:
    raise ValueError("Aucune couronne détectée")

gdf_couronnes = gpd.GeoDataFrame(
    couronnes, geometry="geometry", crs=crs
)

gdf_arbres = gpd.GeoDataFrame(
    arbres, geometry="geometry", crs=crs
)

Path(SORTIE).parent.mkdir(parents=True, exist_ok=True)

# Supprimer l'ancien fichier pour éviter des couches obsolètes
Path(SORTIE).unlink(missing_ok=True)

# Un GeoPackage peut contenir plusieurs couches dans un seul fichier.
gdf_couronnes.to_file(
    SORTIE, layer="couronnes", driver="GPKG"
)

gdf_arbres.to_file(
    SORTIE, layer="arbres", driver="GPKG"
)

print(f"Arbres détectés : {len(arbres)}")
print(f"Résultat : {SORTIE}")
