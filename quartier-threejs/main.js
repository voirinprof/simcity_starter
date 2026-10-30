// Étape 7b — Afficher le quartier en 3D avec Three.js.
//
// On charge les GeoJSON produits par export.py et on construit :
//   - les bâtiments, extrudés à leur hauteur LiDAR ;
//   - les arbres, sous forme de tronc + couronne ;
//   - les routes, sous forme de lignes épaisses.

import * as THREE from 'https://esm.sh/three@0.180.0';
import { OrbitControls } from 'https://esm.sh/three@0.180.0/addons/controls/OrbitControls.js';
// Line2 permet des lignes d'épaisseur réelle (les lignes WebGL classiques font 1 pixel).
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';

// --- Mise en place de la scène ---------------------------------------------

// La scène contient tous les objets à afficher.
const scene = new THREE.Scene();
scene.background = new THREE.Color('#dbe9f0');

// Caméra en perspective : angle de vue 55°, objets visibles entre 1 et 10 000 m.
const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 1, 10000);
camera.position.set(180, 220, 260);

// Le renderer dessine la scène dans un <canvas> ajouté à la page.
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);

// OrbitControls : tourner, zoomer et se déplacer à la souris autour d'une cible.
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);   // Le centre du quartier (voir export.py)
controls.update();

// Éclairage : une lumière d'ambiance ciel/sol + un "soleil" directionnel
// qui donne du relief aux façades.
scene.add(new THREE.HemisphereLight(0xffffff, 0x879a9a, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 2);
sun.position.set(100, 250, 120);
scene.add(sun);

// Sol : un grand plan de 2 km, couché à l'horizontale
// (un PlaneGeometry est vertical par défaut, d'où la rotation de -90°).
const sol = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000), new THREE.MeshLambertMaterial({ color: '#b6c9a8' }));
sol.rotation.x = -Math.PI / 2;
scene.add(sol);

// --- Conversion des géométries GeoJSON -------------------------------------

// GeoJSON en mètres, centré autour de (0,0).
// Three.js : X=Est, Y=hauteur, Z=-Nord.
const xy = ([x, y]) => [x, -y];

// Un anneau GeoJSON répète son premier point à la fin : on retire ce doublon.
function anneau(coords) {
  const points = coords.slice(0, -1).map(([x, y]) => new THREE.Vector2(x, y));
  return points;
}

// Un polygone GeoJSON = [contour extérieur, trou 1, trou 2, …].
// THREE.Shape décrit une forme 2D, avec ses trous éventuels.
function forme(polygon) {
  const shape = new THREE.Shape(anneau(polygon[0]));
  for (const hole of polygon.slice(1)) shape.holes.push(new THREE.Path(anneau(hole)));
  return shape;
}

// Renvoie toujours une liste de polygones, que la géométrie soit
// un Polygon ou un MultiPolygon (plusieurs parties).
function polygones(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return [geometry.coordinates];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates;
  return [];
}

// Même principe pour les lignes : LineString ou MultiLineString.
function lignes(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'LineString') return [geometry.coordinates];
  if (geometry.type === 'MultiLineString') return geometry.coordinates;
  return [];
}

// Télécharge data/<nom>.geojson et renvoie la liste de ses entités.
async function charger(nom) {
  const r = await fetch(`./data/${nom}.geojson`);
  if (!r.ok) throw new Error(`${nom}: HTTP ${r.status}`);
  return (await r.json()).features;
}

// --- Construction des objets 3D --------------------------------------------

function ajouterBatiments(features) {
  for (const f of features) {
    // Sans hauteur LiDAR valide (étape 4), on n'affiche pas le bâtiment.
    const hauteur = Number(f.properties.hauteur_m);
    if (!Number.isFinite(hauteur) || hauteur <= 0) continue;
    // Couleur du toit tirée de l'orthophoto, ou beige par défaut.
    const couleur = f.properties.couleur || '#b9a28e';
    for (const poly of polygones(f.geometry)) {
      // Extrusion : on "tire" l'emprise 2D sur la hauteur du bâtiment.
      const geo = new THREE.ExtrudeGeometry(forme(poly), { depth: hauteur, bevelEnabled: false });
      // ExtrudeGeometry extrude suivant Z : transformer en hauteur Y.
      geo.rotateX(-Math.PI / 2);
      // Après rotation, Z=-nord : cohérent avec les arbres et les routes.
      const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: couleur, side: THREE.DoubleSide }));
      scene.add(mesh);
    }
  }
}

function ajouterArbres(features) {
  // Matériaux et géométries créés une seule fois et partagés par tous
  // les arbres : beaucoup plus économe en mémoire.
  const matTronc = new THREE.MeshLambertMaterial({ color: '#775437' });
  const matFeuille = new THREE.MeshLambertMaterial({ color: '#3f8b4e' });
  const troncGeo = new THREE.CylinderGeometry(0.23, 0.32, 1, 6);   // Hauteur 1, mise à l'échelle ensuite
  const bouleGeo = new THREE.SphereGeometry(1, 9, 7);              // Rayon 1, mise à l'échelle ensuite
  for (const f of features) {
    if (f.geometry?.type !== 'Point') continue;
    // Valeurs par défaut si l'attribut est absent
    const h = Number(f.properties.hauteur_m) || 8;
    const rayon = Number(f.properties.rayon_m) || 2.5;
    const [x, z] = xy(f.geometry.coordinates);
    // Tronc : 60 % de la hauteur, posé sur le sol (centre à mi-hauteur).
    const hauteurTronc = h * 0.6;
    const tronc = new THREE.Mesh(troncGeo, matTronc);
    tronc.scale.set(1, hauteurTronc, 1);
    tronc.position.set(x, hauteurTronc / 2, z);
    scene.add(tronc);
    // Couronne : sphère aplatie, élargie au rayon de l'arbre.
    const couronne = new THREE.Mesh(bouleGeo, matFeuille);
    couronne.scale.set(rayon, Math.max(1, h * 0.35), rayon);
    couronne.position.set(x, h * 0.7, z);
    scene.add(couronne);
  }
}

function ajouterRoutes(features) {

    for (const f of features) {

        // Type de route OSM (tag "highway")
        const type = f.properties?.highway ?? "residential";

        // Largeur approximative de la chaussée selon le type (en mètres)
        const largeur = type === "primary" ? 9 :
                        type === "secondary" ? 7 :
                        type === "residential" ? 6 : 3;

        // worldUnits: true → l'épaisseur est en mètres de la scène,
        // et non en pixels : les routes s'affinent quand on s'éloigne.
        const mat = new LineMaterial({
            color: 0x66686a,
            linewidth: largeur,
            worldUnits: true
        });

        for (const line of lignes(f.geometry)) {
            if (line.length < 2) continue;

            // Liste à plat [x1, y1, z1, x2, y2, z2, …].
            // Légèrement au-dessus du sol (0,15 m) pour ne pas se confondre avec lui.
            const positions = line.flatMap(([x, y]) => [
                x, 0.15, -y
            ]);

            const geo = new LineGeometry();
            geo.setPositions(positions);

            const route = new Line2(geo, mat);
            route.computeLineDistances();

            scene.add(route);
        }
    }
}

// --- Chargement des données et boucle d'affichage --------------------------

// Les trois fichiers sont téléchargés en parallèle.
try {
  const [batiments, arbres, routes] = await Promise.all([
    charger('batiments'), charger('arbres'), charger('routes')
  ]);
  ajouterBatiments(batiments);
  ajouterArbres(arbres);
  ajouterRoutes(routes);
  console.log('Chargé :', batiments.length, 'bâtiments,', arbres.length, 'arbres,', routes.length, 'routes');
} catch (e) {
  // En cas d'erreur (fichier manquant, page ouverte sans serveur…),
  // on l'affiche directement dans le bandeau de titre.
  console.error(e);
  document.querySelector('#titre').textContent = `Erreur : ${e.message}`;
}

// Adapter la caméra et le canvas quand la fenêtre change de taille.
window.addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// Boucle d'animation : redessine la scène à chaque image (~60 fois par seconde).
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
