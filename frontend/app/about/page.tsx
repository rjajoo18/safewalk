"use client";

import { ArrowLeft, Footprints } from "lucide-react";
import Link from "next/link";

const GALLERY = [
  {
    src: "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1400&q=80",
    alt: "Atlanta street corridor with transit and traffic",
    caption: "The transit trip is often solved. The walk after it is not."
  },
  {
    src: "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?auto=format&fit=crop&w=1200&q=80",
    alt: "Dense Atlanta roadway and job corridor at dusk",
    caption: "Safewalk is built around the corridors where riders depend on walking most."
  }
];

export default function AboutPage() {
  return (
    <main className="about-page-shell">
      <AboutNav />
      <section className="about-wrap">
        <header className="about-hero">
          <article className="about-card about-copy-card">
            <p className="about-kicker">The Problem</p>
            <div className="about-prose">
              <p>
                Atlanta&apos;s transit riders face a quiet mobility crisis that the maps don&apos;t show.
                MARTA can get you close, but in South Atlanta&apos;s job corridors, the last mile is often an unlit,
                sidewalk-less arterial that&apos;s genuinely dangerous to walk.
              </p>
              <p>
                Workers at the Gillem Logistics Center walk 1.5–2 miles along busy roadways with no sidewalk after
                exiting MARTA, not as an edge case, but as the daily commute (Georgia Tech / ARC, 2022). Atlanta
                ranks among the most dangerous U.S. cities for pedestrians, and that risk is concentrated exactly
                where people are most dependent on transit and least likely to have a car as a backup.
              </p>
              <p>
                Google Maps will show you the shortest route. It won&apos;t tell you whether there&apos;s a sidewalk on it.
              </p>
            </div>
          </article>
          <figure className="about-hero-image">
            <img src={GALLERY[0].src} alt={GALLERY[0].alt} />
            <figcaption>{GALLERY[0].caption}</figcaption>
          </figure>
        </header>

        <section className="about-section-grid">
          <article className="about-card about-copy-card">
            <p className="about-kicker">The Solution</p>
            <div className="about-prose">
              <p>
                Safewalk is a safe-routing web app that finds the <em>safest</em> walking route between any two points,
                whether that&apos;s a MARTA stop and your workplace or any other origin and destination, and shows you
                exactly why one path is safer than another.
              </p>
              <p>
                Every street segment in the network is scored across nine factors: sidewalk coverage, traffic risk
                (speed class + volume), pedestrian crash history, reported hazards, tree canopy shade, heat exposure,
                terrain slope, crossing danger, and flood risk. Those scores are built from open data including OSM
                footways, Clayton County ARC sidewalk geometry, GDOT traffic counts, Atlanta 311 reports, and NIHHIS
                heat rasters, and pre-baked across 30,000+ segments covering the Gillem corridor.
              </p>
              <p>
                The interface shows two routes side by side: the default (fastest) in red, the safest in green,
                colored per-segment by risk. Three sliders let you weight what matters most: sidewalks, safety, or
                comfort. A wheelchair-accessible toggle hard-avoids stairs, steep grades, and inaccessible crossings
                entirely. Switching to dark mode shifts to a night routing profile, automatically boosting the weight
                on traffic and crash risk when visibility drops.
              </p>
              <p>
                Where no safe route exists, riders can tap to flag the gap. Reports are anonymous, geotagged, and
                timestamped, and feed a live heatmap designed to function as a Vision Zero deliverable the city can act on.
              </p>
              <p>
                Walking is the only free, universal, no-app, no-bank first/last-mile mode. Making the walk safe is what
                makes transit actually accessible.
              </p>
            </div>
          </article>

          <figure className="about-side-image">
            <img src={GALLERY[1].src} alt={GALLERY[1].alt} />
            <figcaption>{GALLERY[1].caption}</figcaption>
          </figure>
        </section>

        <section className="about-sources-grid">
          <article className="about-card about-source-card">
            <p className="about-kicker">Sources</p>
            <h3>Research</h3>
            <ul>
              <li>
                Georgia Tech / Atlanta Regional Commission, <em>MARTA Reach: First/Last-Mile Access Study</em>, 2022
              </li>
              <li>
                Smart Growth America, <em>Divided by Design: Atlanta&apos;s Story</em>, 2023
              </li>
              <li>
                Brookings Institution, <em>Missed Opportunity: Transit and Jobs in Metropolitan America</em>, 2011
              </li>
              <li>
                U.S. EPA, Transportation as the largest source of U.S. greenhouse gas emissions
              </li>
            </ul>
          </article>

          <article className="about-card about-source-card">
            <p className="about-kicker">Sources</p>
            <h3>Data</h3>
            <ul>
              <li>GDOT TADA, Annual Average Daily Traffic (AADT) station data</li>
              <li>NIHHIS-CAPA Atlanta Urban Heat Campaign raster data</li>
              <li>FEMA National Flood Hazard Layer + ARC Floodplain geodata</li>
              <li>OpenStreetMap footway/sidewalk/crossing network data</li>
            </ul>
          </article>
        </section>
      </section>
    </main>
  );
}

function AboutNav() {
  return (
    <nav className="nav">
      <div className="brand">
        <span><Footprints size={21} /></span>
        Safewalk
      </div>
      <div className="nav-links">
        <Link href="/">Map</Link>
        <Link className="active" href="/about">About</Link>
      </div>
      <Link className="report-back-link" href="/">
        <ArrowLeft size={17} />
        Map
      </Link>
    </nav>
  );
}
