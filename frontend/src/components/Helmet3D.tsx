import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { Suspense, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Box3, Group, PMREMGenerator, Vector3 } from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

const MODEL = '/models/helmet.glb'
/** How far the head turns to meet the cursor, in radians. It looks; it does
 *  not move — the helmet stays centred in its frame. */
const MAX_YAW = 0.62
const MAX_PITCH = 0.34
const MAX_ROLL = 0.1
/** Pops in when the model is ready, not when the canvas mounts. */
const IN_MS = 620
/** Per-frame approach rate. Damped rather than snapped, so a fast mouse does
 *  not throw it around. */
const EASE = 6

const clamp01 = (n: number) => Math.min(Math.max(n, 0), 1)
/** Back-out: overshoots past 1 and settles, which is what reads as a pop. */
const popOut = (t: number) => {
  const c = 1.70158 + 1
  return 1 + c * Math.pow(t - 1, 3) + 1.70158 * Math.pow(t - 1, 2)
}

function hasWebGL() {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

function Studio() {
  const gl = useThree((s) => s.gl)
  const scene = useThree((s) => s.scene)
  const texture = useMemo(() => {
    try {
      const pmrem = new PMREMGenerator(gl)
      const rt = pmrem.fromScene(new RoomEnvironment(), 0.04)
      pmrem.dispose()
      return rt.texture
    } catch {
      return null
    }
  }, [gl])

  useEffect(() => {
    if (texture) scene.environment = texture
    return () => {
      texture?.dispose()
      scene.environment = null
    }
  }, [texture, scene])
  return null
}

function Helmet({ onReady, pointer }: { onReady: () => void; pointer: RefObject<{ x: number; y: number }> }) {
  const { scene } = useGLTF(MODEL, '/draco/gltf/')
  const group = useRef<Group>(null)
  const start = useRef(0)

  // The model is barely 5cm across in its own units and sits off-origin, so it
  // is centred and normalised to a fixed on-screen size rather than trusted to
  // arrive camera-ready.
  const fit = useMemo(() => {
    const box = new Box3().setFromObject(scene)
    const c = box.getCenter(new Vector3())
    const size = box.getSize(new Vector3())
    return { offset: new Vector3(-c.x, -c.y, -c.z), scale: 1.5 / Math.max(size.x, size.y, size.z) }
  }, [scene])

  useEffect(() => {
    start.current = performance.now()
    onReady()
  }, [onReady])

  useFrame((_, delta) => {
    const g = group.current
    if (!g) return

    const t = clamp01((performance.now() - start.current) / IN_MS)
    g.scale.setScalar(fit.scale * popOut(t))

    // Rotation only: the helmet holds its place and turns to face the cursor.
    // Damped, and delta-scaled so the approach is the same at any framerate.
    const k = 1 - Math.exp(-EASE * delta)
    const px = pointer.current?.x ?? 0
    const py = pointer.current?.y ?? 0
    g.rotation.y += (px * MAX_YAW - g.rotation.y) * k
    g.rotation.x += (-py * MAX_PITCH - g.rotation.x) * k
    g.rotation.z += (-px * MAX_ROLL - g.rotation.z) * k
  })

  return (
    <group ref={group} scale={0}>
      <primitive object={scene} position={fit.offset} />
    </group>
  )
}

export function Helmet3D() {
  const [visible, setVisible] = useState(false)
  const [failed, setFailed] = useState(() => !hasWebGL())
  const [ready, setReady] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  /** Pointer position relative to the canvas centre, -1..1. Tracked on the
   *  window rather than the canvas so the helmet keeps following once the
   *  cursor leaves its box — which, given how small the box is, is most of the
   *  time. A ref, not state: this updates on every mouse move. */
  const pointer = useRef({ x: 0, y: 0 })

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const el = wrap.current
      if (!el) return
      const r = el.getBoundingClientRect()
      pointer.current.x = Math.max(-1, Math.min((e.clientX - (r.left + r.width / 2)) / (r.width / 2), 1))
      pointer.current.y = Math.max(-1, Math.min(((r.top + r.height / 2) - e.clientY) / (r.height / 2), 1))
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [])

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), {
      rootMargin: '200px 0px',
    })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  // No silent hole in the page if the browser cannot give us a context.
  if (failed) return null

  return (
    <div
      className={ready ? 'helmet is-ready' : 'helmet'}
      ref={wrap}
      aria-hidden="true"
    >
      <Canvas
        // Only draws while it is on screen; this is the page's second WebGL
        // context and there is no reason for it to run behind the fold.
        frameloop={visible ? 'always' : 'never'}
        dpr={[1, 1.5]}
        camera={{ position: [0, 0.1, 4.2], fov: 30 }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener('webglcontextlost', (e) => {
            e.preventDefault()
            setFailed(true)
          })
        }}
      >
        <Studio />
        <ambientLight intensity={0.5} />
        <pointLight position={[2.6, 3, 3.4]} intensity={18} color="#fff1e2" distance={18} decay={1.6} />
        <pointLight position={[-3, 0.6, -2.4]} intensity={10} color="#ff8a3d" distance={16} decay={1.6} />
        <Suspense fallback={null}>
          <Helmet onReady={() => setReady(true)} pointer={pointer} />
        </Suspense>
      </Canvas>
    </div>
  )
}

useGLTF.preload(MODEL, '/draco/gltf/')
