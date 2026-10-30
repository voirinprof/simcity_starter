# simcity_starter — Construire une scène 3D à partir de données géomatiques

Ce dépôt **pédagogique** présente, pas à pas, les notions de base pour passer de données géographiques ouvertes à une petite scène 3D interactive dans le navigateur (Three.js).

L'exemple porte sur un quartier de **500 m × 500 m à Sherbrooke (Québec)**. Chaque script est volontairement court et se concentre sur **une seule idée**. Le but est de comprendre la démarche, pas d'avoir un outil complet.

> Ces principes sont repris dans un dépôt plus complet où j'automatise la chaîne complète (téléchargement, préparation des données, génération de la scène).

---

## Données ouvertes et licences

Ce projet utilise **uniquement des données ouvertes**. « Ouvert » ne veut pas dire « sans conditions » : chaque source a sa propre licence, avec en général une **obligation d'attribution** et parfois des conditions de partage.

**Avant de réutiliser, publier ou redistribuer des données (ou une scène qui en dérive), vérifiez et respectez la licence de chaque source.**

| Source | Utilisée dans | Licence (à vérifier sur le site officiel) |
|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | `step1.py`, `step2.py`, routes | ODbL — attribution « © les contributeurs d'OpenStreetMap », partage à l'identique des bases de données dérivées |
| [Référentiel bâtiment du Québec](https://www.donneesquebec.ca/) | `step2.py` | Licence indiquée sur Données Québec (généralement CC BY 4.0) |
| [Sentinel-2 (Copernicus)](https://sentinels.copernicus.eu/) via [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) | `step3.py` | Données Copernicus libres et gratuites — mention « Contient des données Copernicus Sentinel modifiées [année] » ; conditions d'utilisation du Planetary Computer |
| LiDAR et modèle numérique de terrain du Québec (ex. [Forêt ouverte](https://www.foretouverte.gouv.qc.ca/)) | `step4.py`, `step5.py`, `step6.py` | Licence indiquée par le fournisseur (généralement CC BY 4.0) |
| Orthophotographie - [Imagerie orthorectifiée du Québec](https://www.donneesquebec.ca/) |`step4.py` | Licence indiquée sur Données Québec (généralement CC BY 4.0) |

Les licences peuvent changer : le tableau ci-dessus est indicatif, seule la page officielle de chaque fournisseur fait foi. Les données ne sont pas redistribuées dans ce dépôt.

---

## Vue d'ensemble de la démarche

```
 Délimiter une zone ──► Récupérer des données ──► Enrichir (hauteurs, couleurs, arbres) ──► Exporter ──► Afficher en 3D
```

Trois idées reviennent dans toutes les étapes :

1. **Travailler en mètres.** Les coordonnées GPS (EPSG:4326) sont en degrés. Pour mesurer des distances, des surfaces ou des hauteurs, on reprojette dans un système métrique (ici UTM 19N, EPSG:32619, ou le système d'origine des données LiDAR).
2. **Ne charger que la zone utile.** On découpe toujours les données autour du quartier (`clip`, `bbox`, fenêtre raster) pour garder des traitements rapides.
3. **Vérifier visuellement.** Chaque étape produit une image PNG pour contrôler le résultat avant de passer à la suivante.

---

## Les étapes

### Étape 1 — Délimiter un quartier et interroger OpenStreetMap (`step1.py`)

- On part d'un point (latitude, longitude) au centre de Sherbrooke.
- On le reprojette en UTM pour pouvoir tracer un **carré de 500 m** autour (`buffer` avec `cap_style=3` = coins carrés).
- On interroge OpenStreetMap avec **OSMnx** pour récupérer bâtiments, routes, parcs et stationnements.
- On sépare les objets par catégorie et on les affiche.

**Notions :** systèmes de coordonnées (CRS), reprojection, emprise d'étude, tags OSM.
**Sortie :** `quartier_osm.png`

### Étape 2 — Comparer deux sources de bâtiments (`step2.py`)

- On récupère les bâtiments OSM de la même zone.
- On lit le **Référentiel bâtiment du Québec** (GeoPackage) en ne chargeant que l'emprise utile (`bbox`), après l'avoir exprimée dans le CRS du fichier.
- On affiche les deux sources côte à côte avec le nombre d'objets.

**Notions :** qualité et complétude des données, lecture partielle d'un gros fichier, choix d'une source.
**Entrée :** `data/sources/Referentiel_batiment.gpkg` (à télécharger sur Données Québec)
**Sortie :** `comparaison_batiments.png`

### Étape 3 — Détecter la végétation par satellite (`step3.py`)

- On interroge un **catalogue STAC** (Microsoft Planetary Computer) pour trouver des images **Sentinel-2** de l'été 2025 avec moins de 10 % de nuages.
- On garde l'image la moins nuageuse et on lit **seulement la fenêtre** correspondant au quartier, pour les bandes rouge (B04) et proche infrarouge (B08).
- On calcule le **NDVI** = (PIR − Rouge) / (PIR + Rouge) et on applique un seuil (0,3) pour repérer la végétation.

**Notions :** catalogues STAC, imagerie multispectrale, lecture par fenêtre, indice de végétation.
**Sortie :** `vegetation_stac.png`

### Étape 4 — Donner une hauteur et une couleur aux bâtiments (`step4.py`)

- On charge les emprises de bâtiments et un nuage de points **LiDAR** (`.laz`).
- On calcule la **hauteur normalisée** de chaque point : altitude du point − altitude du terrain (MNT).
- Pour chaque bâtiment, on prend les points à l'intérieur de l'emprise (légèrement rétrécie pour éviter les arbres voisins) et on retient le **90ᵉ percentile** comme hauteur du toit.
- On échantillonne une grille de pixels dans l'**orthophoto** et on prend la **médiane RGB** comme couleur de toit.
- On exporte les bâtiments enrichis (`hauteur_m`, `nb_points`, `couleur`).

**Notions :** LiDAR, MNT, hauteur normalisée, statistiques robustes (percentile, médiane), jointure point-polygone.
**Sortie :** `data/processed/batiments_3d.gpkg`

### Étape 5 — Isoler les points LiDAR de végétation (`step5.py`)

- On garde les points de classe **1 (« non classés »)**, où se trouve en pratique l'essentiel de la végétation haute.
- On construit des **masques** autour des bâtiments (1 m) et des routes (4 m), puis on retire les points qui tombent dedans.
- On enregistre un nouveau fichier `.laz` qui conserve tous les attributs des points.

**Notions :** classification LiDAR (ASPRS), masques vectoriels, filtrage de nuage de points.
**Sorties :** `data/processed/lidar/points_vegetation.laz`, `lidar_unclassified_masque.png`

### Étape 6 — Détecter les arbres (`step6.py`)

- On normalise les hauteurs avec le MNT et on garde les points au-dessus de 2,5 m.
- **DBSCAN** élimine les points isolés (bruit).
- On rasterise les points en un **modèle de hauteur de canopée (CHM)** de 0,5 m de résolution.
- On lisse le CHM, on détecte les **sommets locaux** (un sommet ≈ un arbre), puis on sépare les couronnes par **ligne de partage des eaux** (*watershed*).
- On vectorise les couronnes et on calcule hauteur, surface et diamètre de chaque arbre.

**Notions :** CHM, partitionnement (DBSCAN), segmentation d'image, passage raster → vecteur.
**Sortie :** `data/processed/lidar/couronnes.gpkg` (couches `couronnes` et `arbres`)

### Étape 7 — Exporter et afficher en 3D (`quartier-threejs/`)

**`export.py`**
- Ramène toutes les couches (bâtiments, arbres, routes) dans le même CRS métrique.
- **Simplifie** les géométries (quelques dizaines de centimètres suffisent pour l'affichage).
- **Recentre** les coordonnées autour de (0, 0) : les moteurs 3D gèrent mal les grandes coordonnées projetées (plusieurs centaines de milliers de mètres).
- Exporte en GeoJSON dans `quartier-threejs/data/`.

**`index.html` + `main.js`**
- Les bâtiments sont **extrudés** à leur hauteur (`ExtrudeGeometry`) avec leur couleur de toit.
- Les arbres sont représentés par un tronc (cylindre) et une couronne (sphère) mis à l'échelle.
- Les routes sont tracées avec une largeur qui dépend de leur type OSM.
- Attention aux axes : en géomatique, Y = Nord ; dans Three.js, **Y = hauteur** et le Nord correspond à **−Z**.

**Notions :** coordonnées locales, simplification, extrusion, conventions d'axes en 3D.

---

## Lancer les scripts

### Prérequis

Python ≥ 3.10 et les bibliothèques suivantes :

```bash
pip install osmnx geopandas matplotlib shapely numpy rasterio \
            pystac-client planetary-computer laspy[lazrs] \
            scikit-learn scikit-image scipy
```

### Données d'entrée

À vous de télécharger les données nécessaires. Certaines étapes vont générer de nouvelles données. 

```
data/
├── sources/Referentiel_batiment.gpkg     # étape 2
├── raw/
│   ├── local/buildings.geojson           # étapes 4, 5
│   ├── local/roads.geojson               # étape 5, export
│   └── ortho/ortho.tif                   # étape 4
└── processed/lidar/
    ├── points_zone.laz                   # étapes 4, 5 (LiDAR découpé sur la zone)
    └── mnt_clipped.tif                   # étapes 4, 6 (MNT découpé sur la zone)
```

La préparation de ces fichiers (téléchargement des tuiles, découpage sur la zone) n'est pas détaillée ici.

### Exécution

```bash
python step1.py
python step2.py
python step3.py
python step4.py
python step5.py
python step6.py

cd quartier-threejs
python export.py
python -m http.server 8000
# puis ouvrir http://localhost:8000
```

Un serveur local est nécessaire.

