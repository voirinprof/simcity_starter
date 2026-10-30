"""
Étape 3 — Détecter la végétation avec une image satellite.

On cherche une image Sentinel-2 peu nuageuse dans un catalogue STAC,
on lit seulement la portion qui couvre le quartier, puis on calcule
l'indice de végétation NDVI.

Données : contient des données Copernicus Sentinel modifiées,
servies par Microsoft Planetary Computer (voir leurs conditions).
"""

import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import rasterio                      # Lecture de rasters (GeoTIFF, COG…)
import planetary_computer            # Signature des URL du Planetary Computer
from pystac_client import Client     # Client pour interroger un catalogue STAC
from shapely.geometry import Point
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

# Paramètres
LAT, LON = 45.4042, -71.8929
COTE = 500
PERIODE = "2025-06-01/2025-08-31"  # Été : la végétation est bien visible
SEUIL_NDVI = 0.3                    # Au-dessus : végétation probable

# Zone de 500 m en UTM
centre = gpd.GeoSeries(
    [Point(LON, LAT)], crs=4326
).to_crs(32619)
zone = centre.iloc[0].buffer(COTE / 2, cap_style=3)
# Le catalogue STAC attend une emprise en degrés (lon/lat).
bbox = gpd.GeoSeries([zone], crs=32619).to_crs(4326).total_bounds

# Recherche dans le catalogue STAC
# STAC (SpatioTemporal Asset Catalog) est un standard pour décrire
# et rechercher des images par lieu, date et propriétés.
# sign_inplace ajoute automatiquement un jeton d'accès aux URL des fichiers.
catalogue = Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace
)

# Sentinel-2 niveau L2A = réflectance de surface (corrigée de l'atmosphère).
# On ne garde que les images avec moins de 10 % de nuages.
resultats = catalogue.search(
    collections=["sentinel-2-l2a"],
    bbox=bbox.tolist(),
    datetime=PERIODE,
    query={"eo:cloud_cover": {"lt": 10}},
    max_items=30
)

# On trie les images de la moins nuageuse à la plus nuageuse.
images = sorted(
    resultats.items(),
    key=lambda i: i.properties.get("eo:cloud_cover", 100)
)
if not images:
    raise RuntimeError("Aucune image trouvée")

image = images[0]
print("Image :", image.datetime)
print("Nuages :", image.properties["eo:cloud_cover"], "%")

# Lire une petite fenêtre de chaque bande
# Une tuile Sentinel-2 fait environ 110 × 110 km : on ne télécharge
# que la "fenêtre" de pixels qui recouvre notre carré de 500 m.
def lire_bande(nom):
    with rasterio.open(image.assets[nom].href) as src:
        # Emprise du quartier exprimée dans le CRS de l'image
        limites = transform_bounds(
            "EPSG:32619", src.crs, *zone.bounds
        )
        # Conversion des coordonnées en lignes/colonnes de pixels
        fenetre = from_bounds(*limites, transform=src.transform)
        fenetre = fenetre.round_offsets().round_lengths()
        valeurs = src.read(1, window=fenetre).astype(float)
        # On renvoie aussi le géoréférencement propre à cette fenêtre
        return valeurs, src.window_transform(fenetre)

# B04 = rouge, B08 = proche infrarouge (PIR), à 10 m de résolution
rouge, transform = lire_bande("B04")
pir, _ = lire_bande("B08")

# Calcul du NDVI et extraction de la végétation
# NDVI = (PIR - Rouge) / (PIR + Rouge), entre -1 et 1.
# La végétation réfléchit fortement le PIR et absorbe le rouge : NDVI élevé.
# np.divide(..., where=...) évite la division par zéro (résultat NaN).
ndvi = np.divide(
    pir - rouge, pir + rouge,
    out=np.full_like(rouge, np.nan),
    where=(pir + rouge) > 0
)
# Masque booléen : True là où le NDVI dépasse le seuil
vegetation = (ndvi > SEUIL_NDVI) & np.isfinite(ndvi)

# Résultat visuel
fig, axes = plt.subplots(1, 2, figsize=(11, 5))

# Palette rouge → jaune → vert : sol nu / bâti en rouge, végétation en vert
im = axes[0].imshow(ndvi, cmap="RdYlGn", vmin=-1, vmax=1)
axes[0].set_title("NDVI Sentinel-2")
fig.colorbar(im, ax=axes[0], shrink=0.8)

axes[1].imshow(vegetation, cmap="Greens", vmin=0, vmax=1)
axes[1].set_title("Végétation potentielle")

for ax in axes:
    ax.axis("off")

plt.tight_layout()
plt.savefig("vegetation_stac.png", dpi=180)
#plt.show()
