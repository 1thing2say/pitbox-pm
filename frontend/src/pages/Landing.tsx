import { useState, type ReactNode } from 'react'
import { Suspense, lazy } from 'react'
import { Link, useNavigate } from 'react-router-dom'

/* three.js is ~950 KB. Lazy so it never sits in the critical path — the
   wordmark paints first and the car arrives when it is ready. */
const HeroCar3D = lazy(() =>
  import('../components/HeroCar3D').then((m) => ({ default: m.HeroCar3D })),
)


import {
  FeatureAccordion,
  PhaseTabs,
} from '../components/LandingSections'
import { LifeField } from '../components/LifeField'
import { Starfield } from '../components/Starfield'
import { SiteFooter } from '../components/SiteFooter'
import { SiteNav } from '../components/SiteNav'
import { useHeroScroll } from '../hooks/useHeroScroll'
import { useReveal } from '../hooks/useReveal'

/** Static events are judged; dynamic events are driven. */
const STATIC_EVENTS = [
  {
    name: 'Design',
    body: 'You defend the car to practising engineers — why this geometry, why this material, why you rejected the other three options.',
  },
  {
    name: 'Cost',
    body: 'A full bill of materials and manufacturing cost for the vehicle, audited against the car you actually brought.',
  },
  {
    name: 'Sales presentation',
    body: 'Pitch the car to judges playing a manufacturing firm. It is an engineering competition with a business case attached.',
  },
]

const DYNAMIC_EVENTS = [
  { name: 'Acceleration', body: 'Straight-line sprint from a standing start.' },
  { name: 'Maneuverability', body: 'A tight, gated course against the clock.' },
  { name: 'Hill climb / traction', body: 'Pulling load or climbing grade — the event varies by competition.' },
  { name: 'Suspension & traction', body: 'Rough terrain, logs, rocks, ditches. Where cars break.' },
]

const CHEV = (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path d="M6 3l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

/**
 * A visual slot in a bezel. Pass `src` and it renders the screenshot; leave it
 * off and it renders a labelled placeholder at the same aspect ratio, so the
 * layout is already final and dropping a real image in later changes one line
 * and shifts nothing.
 */
function ShotSlot({
  src,
  alt = '',
  label,
  hint,
}: {
  src?: string
  alt?: string
  label: string
  hint?: string
}) {
  if (src) return <img className="shot" src={src} alt={alt} loading="lazy" />
  return (
    <div className="shot shot-empty" role="img" aria-label={`Placeholder — ${label}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
        <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
        <circle cx="8.5" cy="10" r="1.6" />
        <path d="M4 17l4.5-4.5 3.5 3.5 3-2.5L20 18" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="shot-label">{label}</span>
      {hint ? <span className="shot-hint">{hint}</span> : null}
    </div>
  )
}

const ICONS = {
  flag: <path d="M4 21V4m0 0h11l-2 4 2 4H4" strokeLinecap="round" strokeLinejoin="round" />,
  engine: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3v2.4M12 18.6V21M3 12h2.4M18.6 12H21M5.6 5.6l1.7 1.7M16.7 16.7l1.7 1.7M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7" strokeLinecap="round" />
    </>
  ),
  course: <path d="M4 6h16M4 12h10M4 18h13" strokeLinecap="round" />,
  tree: (
    <>
      <path d="M6 4v11a2 2 0 0 0 2 2h4M12 10H8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="5" cy="4" r="1.6" />
      <circle cx="14" cy="10" r="1.6" />
      <circle cx="14" cy="17" r="1.6" />
    </>
  ),
}

/** GitHub's repeated unit: glyph, centred headline, centred sub, then a visual. */
function GhSection({
  id,
  icon,
  tone = '',
  title,
  sub,
  tail,
  children,
}: {
  id?: string
  icon: ReactNode
  tone?: string
  title: string
  sub: string
  tail?: boolean
  children?: ReactNode
}) {
  const ref = useReveal<HTMLElement>()
  return (
    <section id={id} ref={ref} className={`gh-section reveal${tail ? ' tail' : ''}`}>
      <div className={`gh-mark ${tone}`.trim()} aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          {icon}
        </svg>
      </div>
      <h2 className="gh-h">{title}</h2>
      <p className="gh-sub">{sub}</p>
      {children}
    </section>
  )
}

/**
 * GitHub leads with a field, not a button. It carries the address to /signup so
 * nothing is silently swallowed — the account still gets created there, behind
 * the invite code.
 */
function EmailCapture() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  return (
    <form
      className="emailcap-row"
      onSubmit={(e) => {
        e.preventDefault()
        navigate(`/signup?email=${encodeURIComponent(email)}`)
      }}
    >
      <div className="emailcap">
        <input
          type="email"
          required
          placeholder="you@school.edu"
          aria-label="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button type="submit" className="btn btn-primary">
          Request access
        </button>
      </div>
      <Link to="/app" className="btn btn-ghost btn-lg">
        Try the demo tree
      </Link>
    </form>
  )
}

function PhaseSection() {
  const ref = useReveal<HTMLElement>()
  return (
    <section ref={ref} className="gh-section reveal">
      <h2 className="gh-h">One tracker, the whole season</h2>
      <p className="gh-sub">
        The car changes shape from October to competition. The tree changes with it.
      </p>
      <div style={{ marginTop: 'clamp(26px, 4vw, 44px)' }}>
        <PhaseTabs />
      </div>
    </section>
  )
}

export function Landing() {
  const { sectionRef, stageRef, progressRef, subscribe } = useHeroScroll()
  const introRef = useReveal<HTMLElement>()

  return (
    <div className="site">
      <SiteNav />

      <main>
        {/* ===== Hero ===== */}
        {/* Nothing but the grid, the name and the car. The stage is pinned, so
            scrolling here dissolves the wordmark without moving the page. */}
        <section className="hero" ref={sectionRef}>
          <div className="hero-stage" ref={stageRef}>
            <div
              className="hero-bg"
              style={{ contain: 'layout style paint' }}
              aria-hidden="true"
            >
              <LifeField className="hero-life" />
              {/* <div className="hero-grids">
                <span className="grid-a" />
                <span className="grid-b" />
              </div> */}
              <div className="hero-mask" />
              <div className="hero-bottom" />
            </div>

            <h1 className="hero-mark">
              <span className="hero-mark-in">
                <span className="hm-thin">Pit</span> <span className="hm-bold">Box</span>
              </span>
            </h1>

            <Suspense fallback={null}>
              <HeroCar3D progress={progressRef} subscribe={subscribe} />
            </Suspense>

            <div className="hero-card">
              <ShotSlot
                src="/shots/tracker.webp"
                label="The tracker"
                alt="The Pit Box tracker: the Baja 2026 Car part tree with Front Upright, LH selected, showing its part number, status, assignee, material, mass and unit cost alongside the breakdown by material."
              />
            </div>

            {/* The header's actions live here first, under the car. The nav
                only takes over once these have scrolled out of sight. */}
            <div className="hero-cta">
              <Link to="/login" className="btn btn-ghost">
                Log in
              </Link>
              <Link to="/signup" className="btn btn-primary">
                Sign up
              </Link>
            </div>

            <div className="hero-cue" aria-hidden="true">
              <span>Scroll</span>
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M8 3 v9 M4 8.5 l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
        </section>

        {/* ===== Intro — GitHub's hero content, after our brand moment ===== */}
        <section className="gh-section reveal" ref={introRef}>
          <h2 className="gh-h">One car. Every part. One season.</h2>
          <p className="gh-sub">
            Baja SAE teams design, build and race a single-seat off-road vehicle from
            scratch every year. Pit Box is where the team keeps track of every part of
            it — the tree, the status, the files, the people.
          </p>
        </section>


        {/* ===== What is Baja SAE ===== */}
        <GhSection
          id="what"
          icon={ICONS.flag}
          title="Built and raced by students, judged by engineers"
          sub="An intercollegiate competition run by SAE International, part of its Collegiate Design Series."
        >
          <div className="gh-stage">
            <Starfield className="glow-stars" />
            <div className="bezel">
              <div className="bezel-split">
                <div className="bezel-copy">
                  <p className="lead">
                    <b>Every car is a prototype, not a toy.</b> Reliable, maintainable,
                    ergonomic and economical — aimed at a recreational market of roughly
                    four thousand units a year, and it has to fit a driver up to 6'3" and
                    250 lb. A production vehicle does not get to choose its customer.
                  </p>
                  <a className="chev" href="#competition">
                    See how a competition runs {CHEV}
                  </a>
                </div>
                <div className="bezel-visual">
                  <ShotSlot
                    src="/car/car-015.webp"
                    label="The car"
                    hint="Replace with a photo of your own car"
                  />
                </div>
              </div>

              <div className="bezel-pad">
                <div className="specs">
                  <div className="spec">
                    <span className="spec-k">Seats</span>
                    <span className="spec-v">1</span>
                  </div>
                  <div className="spec">
                    <span className="spec-k">Built by</span>
                    <span className="spec-v">Students</span>
                  </div>
                  <div className="spec">
                    <span className="spec-k">Rebuilt</span>
                    <span className="spec-v">Every year</span>
                  </div>
                  <div className="spec">
                    <span className="spec-k">Endurance</span>
                    <span className="spec-v">4 hours</span>
                  </div>
                </div>
              </div>

              {/* The ask sits inside the card, under the facts that earn it. */}
              <div className="bezel-pad bezel-cta">
                <EmailCapture />
              </div>
            </div>
          </div>
        </GhSection>

        {/* ===== Season phases — segmented tablist ===== */}
        <PhaseSection />

        {/* ===== The equalizer ===== */}
        <GhSection
          icon={ICONS.engine}
          tone="warm"
          title="Everybody gets the same engine"
          sub="Every car in the series runs the same specified engine. Nobody can buy their way to more power."
        >
          <div className="gh-stage">
            <Starfield className="glow-stars" />
            <div className="bezel bezel-pad">
              <p className="lead">
                <b>If the powertrain is fixed, the car is won somewhere else.</b> Weight,
                geometry, drivetrain efficiency, durability and driver ergonomics — the
                things students can actually engineer.
              </p>
              <div className="pull">
                <p>
                  Briggs &amp; Stratton supplied the series for decades. Kohler took over as
                exclusive supplier for the 2023–2026 seasons, and every car now runs the
                same 14 hp Command Pro CH440.
                </p>
                <p className="muted">
                  It also means a gram saved is a gram earned. Which is why teams track
                  mass on every single part.
                </p>
              </div>
            </div>
          </div>
        </GhSection>

        {/* ===== Competition format ===== */}
        <GhSection
          id="competition"
          icon={ICONS.course}
          tone="cool"
          title="Static, dynamic, then four hours wheel to wheel"
          sub="Static events are judged. Dynamic events are driven. Then everyone races at once."
        >
          <div className="gh-stage">
            <Starfield className="glow-stars" />
            <div className="bezel bezel-pad">
              <div className="event-cols">
                <div className="event-col">
                  <h3 className="event-h">
                    <span className="pill pill-static">Static</span> Judged, not driven
                  </h3>
                  <ul className="event-list">
                    {STATIC_EVENTS.map((e) => (
                      <li key={e.name}>
                        <b>{e.name}</b>
                        <span>{e.body}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="event-col">
                  <h3 className="event-h">
                    <span className="pill pill-dynamic">Dynamic</span> On the course
                  </h3>
                  <ul className="event-list">
                    {DYNAMIC_EVENTS.map((e) => (
                      <li key={e.name}>
                        <b>{e.name}</b>
                        <span>{e.body}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="endurance">
                <div className="endurance-bar" aria-hidden="true">
                  <span className="endurance-fill" />
                </div>
                <div className="endurance-copy">
                  <h3>Then four hours, wheel to wheel</h3>
                  <p>
                    Every team on the same rough course at once, scoring on laps
                    completed. It is where design decisions made in October get audited by
                    the terrain. Cars that were quick all week finish the season on a
                    trailer because of a single bracket.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </GhSection>


        {/* ===== The tool ===== */}
        <GhSection
          id="tool"
          icon={ICONS.tree}
          title="A car is a tree of parts"
          sub="Vehicle → Subsystem → Assembly → Part. Pit Box stores exactly that, as deep as you need."
          tail
        >
          <div className="gh-stage">
            <Starfield className="glow-stars" />
            <div className="bezel bezel-split">
              <div className="bezel-copy">
                <p className="lead">
                  <b>Tag a branch, and everything under it inherits the tag.</b> Including
                  the parts you add next week. Filter to what matters without losing where
                  anything sits in the car.
                </p>
                <Link className="chev" to="/app">
                  Open the tracker {CHEV}
                </Link>
              </div>
              <div className="bezel-visual">
                <ShotSlot
                  label="Tree view — the whole car, one tree"
                  hint="Drop a screenshot at /public/shots/ and pass src"
                />
              </div>
            </div>
          </div>

          <div className="tool-grid">
            <FeatureCard
              title="The whole car, one tree"
              body="Drag to re-parent. Tag a whole branch at once and everything under it inherits the tag — including parts you add next week."
              delay={0}
            />
            <FeatureCard
              title="Filter to what matters"
              body="Isolate the parts pending machining, or everything Electrical assigned to one person, without losing where they sit in the car."
              delay={80}
            />
            <FeatureCard
              title="Connections across the tree"
              body="Link every part that shares a status, vendor, material or tag — even when they live in completely different subsystems."
              delay={160}
            />
            <FeatureCard
              title="Files on the part"
              body="The STEP file lives on the part it describes, versioned, so last week's revision is always recoverable."
              delay={240}
            />
          </div>

          <div className="gh-stage" style={{ marginTop: 'clamp(34px, 6vh, 68px)' }}>
            <Starfield className="glow-stars" />
            <div className="bezel bezel-split">
              <div className="bezel-copy">
                <FeatureAccordion />
              </div>
              <div className="bezel-visual">
                <ShotSlot
                  label="Filters and connections"
                  hint="Drop a screenshot at /public/shots/ and pass src"
                />
              </div>
            </div>
          </div>

          <div className="cta-strip">
            <div>
              <h3>Built for the team that races it.</h3>
              <p className="muted">
                Pit Box is MESA ARC Racing's own tool. Accounts are created by invite.
              </p>
            </div>
            <div className="cta-strip-actions">
              <Link to="/signup" className="btn btn-primary btn-lg">
                Create an account
              </Link>
              <Link to="/app" className="btn btn-ghost btn-lg">
                Try the demo tree
              </Link>
            </div>
          </div>
        </GhSection>


        {/* ===== Closing CTA ===== */}
        <section className="closing">
          <h2 className="gh-h">Every part of the car, in one place</h2>
          <p className="gh-sub">
            Pit Box is MESA ARC Racing's internal part tracker. Request access if you
            are on the team, or look through the demo tree.
          </p>
          <EmailCapture />
        </section>
      </main>

      <SiteFooter />
    </div>
  )
}

function FeatureCard({ title, body, delay }: { title: string; body: string; delay: number }) {
  const ref = useReveal<HTMLDivElement>(delay)
  return (
    <div className="feature reveal" ref={ref}>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  )
}
