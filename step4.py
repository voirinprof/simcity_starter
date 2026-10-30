"""
Étape 4 — Donner une hauteur et une couleur aux bâtiments.

Pour chaque emprise de bâtiment :
  - la hauteur est estimée à partir des points LiDAR situés dessus ;
  - la couleur du toit est lue dans une orthophoto.

Données : LiDAR, MNT et orthophoto issus de sources ouvertes
(vérifier la licence de chaque fournisseur).
"""

from pathlib import Path

import laspy                      # Lecture des fichiers LiDAR .las / .laz
import numpy as np
import geopandas as gpd
import rasterio

from shapely import contains_xy   # Test "point dans polygone" vectorisé (rapide)
from rasterio.warp import transform as reprojeter

# Fichiers
BATIMENTS = "data/raw/local/buildings.geojson"     # Emprises 2D des bâtiments
LAZ = "data/processed/lidar/points_zone.laz"       # Nuage de points LiDAR
MNT = "data/processed/lidar/mnt_clipped.tif"       # Modèle numérique de terrain
ORTHO = "data/raw/ortho/ortho.tif"                 # Photo aérienne RGB
SORTIE = "data/processed/batiments_3d.gpkg"

# Paramètres
HAUTEUR_MIN = 2.5    # On ignore les points à moins de 2,5 m du sol
POINTS_MIN = 10      # Nombre minimal de points pour estimer une hauteur fiable
QUANTILE_TOIT = 90   # Percentile retenu comme hauteur du toit

# 1. Charger les bâtiments et les points LiDAR
las = laspy.read(LAZ)
crs = las.header.parse_crs()   # Le CRS est stocké dans l'en-tête du fichier

if crs is None:
    raise ValueError("CRS du LiDAR absent")

# On met les bâtiments dans le même CRS que le LiDAR,
# puis on retire les géométries vides ou manquantes.
batiments = gpd.read_file(BATIMENTS).to_crs(crs)
batiments = batiments[
    batiments.geometry.notna()
    & ~batiments.geometry.is_empty
].copy()

# Coordonnées des points sous forme de tableaux NumPy
x = np.asarray(las.x)
y = np.asarray(las.y)
z = np.asarray(las.z)   # z = altitude (au-dessus du niveau de la mer)

print(f"Bâtiments : {len(batiments)}")
print(f"Points LiDAR : {len(x):,}")

# 2. Calculer la hauteur des points au-dessus du MNT
# Le LiDAR donne une altitude absolue. Pour connaître la hauteur
# d'un objet, on soustrait l'altitude du sol (MNT) au même endroit.
with rasterio.open(MNT) as src:
    if src.crs is None:
        raise ValueError("CRS du MNT absent")

    # Si le MNT n'est pas dans le même CRS, on reprojette les points.
    if src.crs != crs:
        mx, my = reprojeter(crs, src.crs, x, y)
    else:
        mx, my = x, y

    # sample() lit la valeur du pixel sous chaque point.
    # Les pixels sans donnée (nodata) deviennent NaN.
    terrain = np.ma.array([
        valeur[0]
        for valeur in src.sample(zip(mx, my), masked=True)
    ]).filled(np.nan)

h = z - terrain   # Hauteur normalisée : 0 = au niveau du sol

# On garde les points valides et suffisamment hauts
valides = np.isfinite(h) & (h > HAUTEUR_MIN)
x, y, h = x[valides], y[valides], h[valides]

# 3. Estimer la hauteur de chaque bâtiment
hauteurs = []
nombres = []

for geom in batiments.geometry:
    # On retire une petite bande au bord du bâtiment
    # pour limiter l'influence des arbres voisins.
    interieur = geom.buffer(-0.5)

    # Bâtiment trop petit : le buffer négatif l'a fait disparaître
    if interieur.is_empty:
        interieur = geom

    # Hauteurs des points qui tombent dans l'emprise
    selection = contains_xy(interieur, x, y)
    valeurs = h[selection]

    nombres.append(len(valeurs))

    # Le 90e percentile est plus robuste que le maximum :
    # un oiseau ou une antenne ne fausse pas le résultat.
    if len(valeurs) >= POINTS_MIN:
        hauteur = np.percentile(valeurs, QUANTILE_TOIT)
        hauteurs.append(round(float(hauteur), 2))
    else:
        hauteurs.append(np.nan)   # Pas assez de points : hauteur inconnue

batiments["hauteur_m"] = hauteurs
batiments["nb_points"] = nombres

# 4. Extraire une couleur représentative du toit
couleurs = []

with rasterio.open(ORTHO) as src:
    if src.crs is None:
        raise ValueError("CRS de l'orthophoto absent")
    if src.count < 3:
        raise ValueError("L'orthophoto doit contenir 3 bandes RGB")

    for geom in batiments.geometry:
        # Plusieurs points dans l'emprise, plutôt
        # qu'un seul pixel au centroïde.
        interieur = geom.buffer(-0.5)
        if interieur.is_empty:
            interieur = geom

        # Grille régulière de 7 × 7 points sur le rectangle englobant
        xmin, ymin, xmax, ymax = interieur.bounds
        xs = np.linspace(xmin, xmax, 7)
        ys = np.linspace(ymin, ymax, 7)

        xx, yy = np.meshgrid(xs, ys)
        px, py = xx.ravel(), yy.ravel()

        # On ne garde que les points de la grille situés sur le toit
        dedans = contains_xy(interieur, px, py)
        px, py = px[dedans], py[dedans]

        if len(px) == 0:
            couleurs.append(None)
            continue

        if src.crs != crs:
            px, py = reprojeter(crs, src.crs, px, py)

        # Valeurs R, G, B (3 premières bandes) sous chaque point
        pixels = np.ma.array([
            valeur[:3]
            for valeur in src.sample(zip(px, py), masked=True)
        ])

        # Éliminer les pixels invalides
        valides_rgb = ~np.ma.getmaskarray(pixels).any(axis=1)
        rgb = np.asarray(pixels[valides_rgb], dtype=float)

        if len(rgb) == 0:
            couleurs.append(None)
            continue

        # Orthophoto supposée en RGB 8 bits
        # La médiane ignore les valeurs extrêmes (ombre, reflet, cheminée).
        rgb = np.clip(np.median(rgb, axis=0), 0, 255)
        r, g, b = rgb.astype(int)

        # Couleur au format hexadécimal, ex. "#A0522D", lisible par Three.js
        couleurs.append(f"#{r:02X}{g:02X}{b:02X}")

batiments["couleur"] = couleurs

# 5. Exporter les bâtiments enrichis
# On crée le dossier si besoin et on supprime l'ancien fichier
# pour repartir d'un GeoPackage propre.
Path(SORTIE).parent.mkdir(parents=True, exist_ok=True)
Path(SORTIE).unlink(missing_ok=True)

batiments.to_file(
    SORTIE,
    layer="batiments",
    driver="GPKG"
)

print(f"Bâtiments avec hauteur : {batiments.hauteur_m.notna().sum()}")
print(f"Résultat : {SORTIE}")
