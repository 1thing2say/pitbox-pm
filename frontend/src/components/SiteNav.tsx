import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'

import { Wordmark } from './Wordmark'

/**
 * The public-site header. Separate from TopBar.tsx, which is the tracker's own
 * toolbar — that one is a working control surface and belongs only to /app.
 */
export function SiteNav({ sticky = true }: { sticky?: boolean }) {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!sticky) return
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [sticky])

  return (
    <header className={['site-nav', sticky ? 'sticky' : '', scrolled ? 'scrolled' : ''].filter(Boolean).join(' ')}>
      <div className="site-nav-inner">
        <Link to="/" className="site-brand" onClick={() => setOpen(false)}>
          {/* The inner span is what animates: on the landing page it waits
              below the header and rises in as the hero wordmark dissolves. */}
          <span className="brand-inner">
            <Wordmark />
          </span>
        </Link>

        <button
          type="button"
          className="nav-burger"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>

        <nav className={['site-links', open ? 'open' : ''].filter(Boolean).join(' ')}>
          <a href="/#what" onClick={() => setOpen(false)}>
            What is Baja?
          </a>
          <a href="/#competition" onClick={() => setOpen(false)}>
            Competition
          </a>
          <a href="/#tool" onClick={() => setOpen(false)}>
            The tool
          </a>
          <NavLink to="/app" onClick={() => setOpen(false)}>
            Tracker
          </NavLink>

          <span className="nav-sep" aria-hidden="true" />

          <Link to="/login" className="btn btn-ghost" onClick={() => setOpen(false)}>
            Log in
          </Link>
          <Link to="/signup" className="btn btn-primary" onClick={() => setOpen(false)}>
            Sign up
          </Link>
        </nav>
      </div>
    </header>
  )
}
