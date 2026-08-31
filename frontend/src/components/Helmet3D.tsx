import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Box3, Group, PMREMGenerator, Vector3 } from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

const MODEL = '/models/helmet.glb'
/** A slow turn — one revolution a minute. Fast enough to read as alive,
 *  slow enough not to pull the eye off the copy underneath it. */
const TURN = (Math.PI * 2) / 60
/** Fades and rises in when the model is ready, not when the canvas mounts. */
const IN_MS = 900

const clamp01 = (n: number) => Math.min(Math.max(n, 0), 1)
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

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

function Helmet({ onReady }: { onReady: () => void }) {
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
    return { offset: new Vector3(-c.x, -c.y, -c.z), scale: 2.1 / Math.max(size.x, size.y, size.z) }
  }, [scene])

  useEffect(() => {
    start.current = performance.now()
    onReady()
  }, [onReady])

  useFrame((_, delta) => {
    const g = group.current
    if (!g) return
    g.rotation.y += TURN * delta
    const t = easeOut(clamp01((performance.now() - start.current) / IN_MS))
    g.scale.setScalar(fit.scale * (0.94 + 0.06 * t))
    g.position.y = (1 - t) * -0.25
  })

  return (
    <group ref={group} scale={fit.scale}>
      <primitive object={scene} position={fit.offset} />
    </group>
  )
}

export function Helmet3D() {
  const [visible, setVisible] = useState(false)
  const [failed, setFailed] = useState(() => !hasWebGL())
  const [ready, setReady] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)

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
          <Helmet onReady={() => setReady(true)} />
        </Suspense>
      </Canvas>
    </div>
  )
}

useGLTF.preload(MODEL, '/draco/gltf/')
