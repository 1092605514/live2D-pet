// Versioned build script - generates timestamped, traceable builds
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const pkgPath = path.join(__dirname, '..', 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));

// Generate build metadata
const now = new Date();
const dateStr = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
const gitHash = (() => {
  try { return execSync('git rev-parse --short HEAD', { cwd: path.join(__dirname, '..') }).toString().trim(); }
  catch { return 'nogit'; }
})();

const buildVersion = `${pkg.version}+${dateStr}.${gitHash}`;
console.log(`Building version: ${buildVersion}`);

// Bump patch version
const [major, minor, patch] = pkg.version.split('.').map(Number);
pkg.version = `${major}.${minor}.${patch + 1}`;
fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n', 'utf8');
console.log(`Version bumped to: ${pkg.version} (for next build)`);

// Set environment variable for electron-builder artifact naming
process.env.BUILD_VERSION = buildVersion;

// Run electron-builder
try {
  execSync('npx electron-builder --win portable --config.win.icon=null', {
    cwd: path.join(__dirname, '..'),
    stdio: 'inherit',
  });
  console.log(`\nBuild complete!`);
  console.log(`Version: ${buildVersion}`);
  console.log(`Output: dist/`);
} catch (e) {
  console.error('Build failed:', e.message);
  process.exit(1);
}
