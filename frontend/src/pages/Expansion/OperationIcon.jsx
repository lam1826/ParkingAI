const paths = {
  car: "M5 17H3V9l2-5h14l2 5v8h-2M5 17v3H3v-3m16 0v3h2v-3M3 10h18M7 14h2m6 0h2M5 17h14",
  camera: "M3 7h4l2-3h6l2 3h4v13H3V7Zm9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z",
  ticket: "M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4V6Zm12 0v3m0 6v3m0-7v2",
  arrow: "M4 12h16m-6-6 6 6-6 6",
};
export default function OperationIcon({ name, style }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name] || paths.car} /></svg>;
}
