// Replaced by the deployment workflow after downloading the immutable build.
// Empty means same-origin; local development still falls back to port 8000.
// School submission: existing DEMO A (verified site ID 2). Remove SINGLE_SITE_ID
// for the general interface, or configure the appropriate ID on another install.
globalThis.__PARKINGAI_CONFIG__ = Object.freeze({ API_URL: "", SINGLE_SITE_ID: 2 });
