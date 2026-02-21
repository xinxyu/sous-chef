#!/usr/bin/env node
/**
 * Injects API_URL from env into environment.prod.ts before build.
 * Use in CI/Vercel: set API_URL in the environment, then run:
 *   node scripts/inject-api-url.js && ng build --configuration=production
 * This keeps the real API URL out of the repo.
 */
const fs = require('fs');
const path = require('path');

const envPath = path.join(__dirname, '..', 'src', 'environments', 'environment.prod.ts');
const apiUrl = process.env.API_URL || '__API_URL__';
// Escape single quotes in URL for the generated TypeScript string
const escaped = apiUrl.replace(/'/g, "\\'");

const content = `/** Injected at build time from API_URL env var (do not commit real URL). */
export const environment = {
  production: true,
  apiUrl: '${escaped}',
};
`;

fs.writeFileSync(envPath, content, 'utf8');
console.log('Injected API_URL into environment.prod.ts');
