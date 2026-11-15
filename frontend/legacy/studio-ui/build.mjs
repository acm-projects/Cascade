import {build} from 'esbuild';
await build({entryPoints:['src/main.jsx'],bundle:true,minify:true,format:'esm',target:['es2022'],
  outfile:'../web/studio/studio.js',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'},legalComments:'eof'});
