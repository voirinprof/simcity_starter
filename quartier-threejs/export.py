"""
Étape 7a — Préparer les données pour Three.js.

On rassemble bâtiments, arbres et routes dans un même système de
coordonnées, on simplifie les géométries, on les recentre autour
de (0, 0) puis on les exporte en GeoJSON pour le navigateur.
"""

from pathlib import Path
import geopandas as gpd

# Couches à exporter : nom → (fichier source, nom de la couche)
SOURCES = {
    "batiments": ("data/processed/batiments_3d.gpkg", "batiments"),
    "arbres": ("data/processed/lidar/couronnes.gpkg", "arbres"),
    "routes": ("data/raw/local/roads.geojson", "roads"),
}

# Tolérances de simplification en mètres
# Simplifier = retirer les sommets inutiles : fichiers plus légers,
# affichage plus rapide, sans différence visible à l'écran.
SIMPLIFICATION = {
    "batiments": 0.3,
    "arbres": 0.0,   # Couche de points : aucune simplification
    "routes": 0.5,
}

# Dossier de sortie lu par la page web
out = Path("data")
out.mkdir(exist_ok=True)

# 1. Charger les couches
layers = {}

for nom, (fichier, couche) in SOURCES.items():
    gdf = gpd.read_file(fichier, layer=couche)

    if gdf.crs is None:
        raise ValueError(f"CRS absent : {nom}")

    # Si la couche est en degrés, on la passe dans la zone UTM adaptée.
    if gdf.crs.is_geographic:
        gdf = gdf.to_crs(gdf.estimate_utm_crs())

    layers[nom] = gdf

# 2. Reprojeter dans un CRS commun
# Le CRS des bâtiments sert de référence pour toutes les couches.
crs = layers["batiments"].crs

for nom in layers:
    layers[nom] = layers[nom].to_crs(crs)

# 3. Déterminer le centre du quartier
# Les coordonnées projetées sont très grandes (centaines de milliers
# de mètres). Les cartes graphiques travaillent en précision limitée :
# de telles valeurs provoquent des tremblements à l'affichage.
# On calcule donc le centre de la zone pour s'en servir d'origine.
bounds = layers["batiments"].total_bounds   # (xmin, ymin, xmax, ymax)

ox = (bounds[0] + bounds[2]) / 2
oy = (bounds[1] + bounds[3]) / 2

# 4. Simplifier et exporter
for nom, gdf in layers.items():

    gdf = gdf.copy()

    tolerance = SIMPLIFICATION[nom]

    # preserve_topology=True évite de créer des polygones invalides
    if tolerance > 0:
        gdf.geometry = gdf.geometry.simplify(
            tolerance=tolerance,
            preserve_topology=True
        )

    # Coordonnées locales pour Three.js
    # Après translation, le centre du quartier est en (0, 0)
    # et les coordonnées restent en mètres.
    gdf.geometry = gdf.geometry.translate(
        xoff=-ox,
        yoff=-oy
    )

    # Export GeoJSON
    fichier_sortie = out / f"{nom}.geojson"

    gdf.to_file(
        fichier_sortie,
        driver="GeoJSON"
    )

    print(
        f"{nom}: {len(gdf)} entités, "
        f"tolérance = {tolerance} m"
    )
