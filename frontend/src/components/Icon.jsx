const paths = {
  home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9M9 20v-6h6v6"/></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></>,
  queue: <><path d="M4 6h16M4 12h16M4 18h10"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  music: <><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></>,
  play: <path d="m8 5 12 7-12 7z" fill="currentColor" stroke="none"/>,
  pause: <><path d="M8 5v14M16 5v14" strokeWidth="3"/></>,
  skip: <><path d="m5 5 10 7-10 7z" fill="currentColor" stroke="none"/><path d="M19 5v14" strokeWidth="3"/></>,
  stop: <rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/>,
  volume: <><path d="M4 10v4h4l5 4V6l-5 4z"/><path d="M17 9a5 5 0 0 1 0 6M19 6a9 9 0 0 1 0 12"/></>,
  shuffle: <><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M4 4l5 5M15 15l6 6"/></>,
  repeat: <><path d="m17 2 4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  x: <><path d="m6 6 12 12M18 6 6 18"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  chevron: <path d="m7 10 5 5 5-5"/>,
  headphones: <><path d="M3 14v-3a9 9 0 0 1 18 0v3"/><path d="M3 14h4v7H6a3 3 0 0 1-3-3zM17 14h4v4a3 3 0 0 1-3 3h-1z"/></>,
  discord: <><path d="M7 7.5A15 15 0 0 1 12 7a15 15 0 0 1 5 .5l1 1A14 14 0 0 1 20 18a12 12 0 0 1-4 2l-1-1.5M8 18l-1 2a12 12 0 0 1-4-2 14 14 0 0 1 2-9.5l1-1"/><circle cx="9" cy="13" r="1" fill="currentColor"/><circle cx="15" cy="13" r="1" fill="currentColor"/></>,
}

export default function Icon({ name, size = 18, className = '' }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
