import {useState,useHostTheme} from 'cursor/canvas';
const groups = [
['Identity / blue','Core',[
['users','Clerk identity reference; no passwords','id text PK (Clerk subject)|display_name text?|created_at timestamptz'],
['user_preferences','One preference record per user','user_id text PK FK users|video_type text|audience text|tone text|goal text|updated_at timestamptz'],
['user_platform_preferences','One selected platform per row','user_id text PK FK users|platform text PK']]],
['Projects & files / green','Core',[
['projects','One creative workspace','id uuid PK|owner_id text FK users|name text|created_at timestamptz|updated_at timestamptz'],
['media_assets','One stored file: upload, rendered MP4, audio, thumbnail or VTT','id uuid PK|project_id uuid FK projects|kind text|storage_backend text|bucket text?|object_key text|original_filename text|mime_type text|byte_size bigint|sha256 text?|duration_ms bigint?|width integer?|height integer?|created_at timestamptz'],
['jobs','One upload, selection, caption-render or research request','id uuid PK|project_id uuid FK projects|parent_job_id uuid? FK jobs|source_asset_id uuid? FK media_assets|kind text|prompt text?|status text|progress numeric|message text?|error_code text?|error_message text?|model text?|config jsonb|created_at timestamptz|started_at timestamptz?|finished_at timestamptz?'],
['job_steps','One timed processing stage / attempt','id uuid PK|job_id uuid FK jobs|name text|attempt integer|status text|started_at timestamptz|finished_at timestamptz?|input_tokens integer?|output_tokens integer?'],
['clips','A selected source interval; not the stored video file itself','id uuid PK|job_id uuid FK jobs|source_asset_id uuid FK media_assets|ordinal integer|title text|source_start_ms bigint|source_end_ms bigint|score numeric?|explanation text?'],
['clip_outputs','Rendered variants and their caption files','id uuid PK|clip_id uuid FK clips|job_id uuid FK jobs|video_asset_id uuid FK media_assets|captions_asset_id uuid? FK media_assets|style text?|created_at timestamptz'],
['saved_clips','A project bookmark of an exact rendered output','project_id uuid PK FK projects|output_id uuid PK FK clip_outputs|saved_at timestamptz']]],
['Speech & research / orange','Core',[
['transcripts','One transcription run for a source asset','id uuid PK|asset_id uuid FK media_assets|language text?|model text|created_at timestamptz'],
['transcript_segments','An ordered speech phrase','id uuid PK|transcript_id uuid FK transcripts|ordinal integer|start_ms bigint|end_ms bigint|text text'],
['transcript_words','Smallest timed speech unit useful for karaoke captions','id uuid PK|segment_id uuid FK transcript_segments|ordinal integer|start_ms bigint|end_ms bigint|text text|confidence numeric?'],
['research_runs','One comparison against current trends','id uuid PK|job_id uuid UNIQUE FK jobs|topic text|summary text?|result jsonb|retrieved_at timestamptz'],
['research_sources','One cited external video in a research run','id uuid PK|research_run_id uuid FK research_runs|provider text|external_id text|url text|title text|channel text?|published_at timestamptz?|observed_views bigint?|rank integer|findings text?']]],
['Editor / purple','Planned',[
['edit_drafts','A saved composition; optimistic version prevents lost saves','id uuid PK|project_id uuid FK projects|name text|version integer|width integer|height integer|fps_num integer|fps_den integer|created_at timestamptz|updated_at timestamptz'],
['timeline_tracks','An ordered video, audio, caption or overlay lane','id uuid PK|draft_id uuid FK edit_drafts|kind text|ordinal integer|muted boolean|locked boolean'],
['timeline_items','One placement of a source file on a track','id uuid PK|track_id uuid FK timeline_tracks|asset_id uuid? FK media_assets|source_in_ms bigint|source_out_ms bigint|timeline_start_ms bigint|playback_rate numeric|volume numeric|text text?|transform jsonb'],
['item_effects','One crop, transition, filter or tracking effect','id uuid PK|item_id uuid FK timeline_items|kind text|ordinal integer|parameters jsonb'],
['effect_keyframes','An animated parameter value at a moment','id uuid PK|effect_id uuid FK item_effects|parameter text|time_ms bigint|value jsonb|interpolation text'],
['caption_styles','Reusable appearance of captions','id uuid PK|project_id uuid FK projects|name text|font_family text|font_size numeric|text_color text|highlight_color text|position_x numeric|position_y numeric|options jsonb'],
['caption_cues','Editable subtitle phrase, independent of original transcript','id uuid PK|track_id uuid FK timeline_tracks|style_id uuid? FK caption_styles|start_ms bigint|end_ms bigint|text text'],
['caption_words','Editable per-word timing within a caption','id uuid PK|cue_id uuid FK caption_cues|ordinal integer|start_ms bigint|end_ms bigint|text text'],
['exports','One render request against a frozen draft snapshot','id uuid PK|draft_id uuid FK edit_drafts|draft_version integer|snapshot jsonb|job_id uuid FK jobs|output_asset_id uuid? FK media_assets|format text|width integer|height integer|created_at timestamptz']]],
['Social content / gray','Optional',[
['social_posts','One generated or edited platform post','id uuid PK|project_id uuid FK projects|clip_id uuid? FK clips|platform text|status text|created_at timestamptz|updated_at timestamptz'],
['social_post_parts','One post body or ordered thread entry','id uuid PK|post_id uuid FK social_posts|ordinal integer|body text'],
['social_connections','One authorized social account; encrypted secret reference only','id uuid PK|user_id text FK users|platform text|external_account_id text|secret_reference text|expires_at timestamptz?'],
['publications','A scheduled publishing attempt and its result','id uuid PK|post_id uuid FK social_posts|connection_id uuid FK social_connections|scheduled_at timestamptz?|status text|external_post_id text?|published_at timestamptz?|error_message text?']]]
];
const paths = [
'users 1 → N projects 1 → N media_assets',
'projects 1 → N jobs 1 → N clips 1 → N clip_outputs',
'jobs 1 → N job_steps; jobs 1 → N child jobs',
'projects N ↔ N clip_outputs through saved_clips',
'media_assets 1 → N transcripts 1 → N transcript_segments 1 → N transcript_words',
'jobs 1 → 0..1 research_runs 1 → N research_sources',
'projects 1 → N edit_drafts 1 → N timeline_tracks 1 → N timeline_items',
'media_assets 1 → N timeline_items; timeline_items 1 → N item_effects 1 → N effect_keyframes',
'caption_styles 1 → N caption_cues; timeline_tracks 1 → N caption_cues 1 → N caption_words',
'edit_drafts 1 → N exports → output media_assets',
'projects 1 → N social_posts 1 → N social_post_parts',
'users 1 → N social_connections; social_posts 1 → N publications ← 1 social_connections'
];
function DatabaseAtlasDetails(){
 const t=useHostTheme();const [scope,setScope]=useState('All');const [q,setQ]=useState('');
 const all=groups.flatMap(g=>(g[2] as string[][]).map(r=>({g:g[0] as string,s:g[1] as string,r})));
 const shown=all.filter(x=>(scope==='All'||x.s===scope)&&x.r.join(' ').toLowerCase().includes(q.toLowerCase()));
 return <main style={{background:t.bg.editor,color:t.text.primary,padding:28,fontFamily:'system-ui',maxWidth:1300,margin:'auto',lineHeight:1.6}}>
 <h1 style={{fontSize:24}}>Cascade database atlas</h1>
 <p>Design proposal • repository inspection, October 18, 2026 • no database changes or live Neon inspection</p>
 <section style={{background:t.fill.tertiary,padding:18}}><strong>15 core tables + 9 editor tables + 4 optional social tables = 28 proposed tables.</strong><p>These are design choices, not a universal minimum. Core includes normalizing transcription currently kept in local files. The active migration defines ONE base table, cascade_app.records (key, payload, updated_at), and FOUR views: projects, settings, jobs, clips. Legacy public tables and Flask code are separate; their live schema is unverified.</p></section>
 <h2>Start your paper here</h2><p>Use blue for identity, green for projects/files/jobs, orange for speech/research, purple for future editing, and gray for optional publishing. Draw rectangles for tables, underline primary keys, circle foreign keys, and use cylinders for local/S3 file storage. Use solid lines for the core proposal and dashed lines for extensions. Color is a paper legend; group labels also identify every table.</p>
 <p><strong>PK</strong> identifies a row. <strong>FK</strong> points to another row. <strong>?</strong> means nullable. <strong>1 → N</strong> means one parent can have many children (including zero). Multiple PK fields form a composite key. Unless marked otherwise, fields are required.</p>
 <h2>Relationship map</h2><div style={{padding:16,border:`1px solid ${t.stroke.primary}`}}>{paths.map(p=><div key={p} style={{fontFamily:'monospace',padding:5}}>{p}</div>)}</div>
 <p>Files live outside Neon. media_assets stores durable object keys and file metadata. Never store a temporary signed URL as the file identity. A clip is a source interval; an output is a rendered variant; a timeline item is a placement. These are separate concepts even when they show the same footage.</p>
 <h2>Unpack every table</h2><div style={{display:'flex',gap:12,marginBottom:20}}><select value={scope} onChange={e=>setScope(e.target.value)}>{['All','Core','Planned','Optional'].map(s=><option key={s}>{s}</option>)}</select><input aria-label="Find a table or field" placeholder="Find a table or field" value={q} onChange={e=>setQ(e.target.value)}/><span>{shown.length} tables shown</span></div>
 {groups.map(g=>{const entries=shown.filter(x=>x.g===g[0]);return entries.length?<section key={g[0] as string}><h3>{g[0] as string} · {g[1] as string}</h3><div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(300px,1fr))',gap:16}}>{entries.map(({r})=><details key={r[0]} open style={{border:`1px solid ${t.stroke.primary}`,padding:14}}><summary><strong>{r[0]}</strong> · {r[2].split('|').length} fields</summary><p style={{color:t.text.secondary}}>{r[1]}</p>{r[2].split('|').map(f=><div key={f} style={{fontFamily:'monospace',fontSize:12,borderTop:`1px solid ${t.stroke.secondary}`,padding:4}}>{f}</div>)}</details>)}</div></section>:null;})}
 <h2>Where decomposition stops</h2><p>Project → source asset → transcript → segment → word → text, start_ms, end_ms. The word is a row; its text and timings are fields. Do not create tables for individual letters, seconds, colors or filenames. Split something into a table when it repeats independently, needs its own identity/history, or must be joined or constrained. Keep flexible model responses and effect settings in JSONB until their structure needs relational rules. Video pixels, audio samples and model weights stay in files.</p>
 <h2>Keys, constraints and indexes to draw beside the boxes</h2><ul><li>Unique: user_platform_preferences(user_id, platform), clips(job_id, ordinal), transcript_segments(transcript_id, ordinal), transcript_words(segment_id, ordinal), timeline_tracks(draft_id, ordinal), caption_words(cue_id, ordinal), social_post_parts(post_id, ordinal). saved_clips uses its two-column primary key.</li><li>Checks: end &gt; start ≥ 0; sizes ≥ 0; dimensions and frame-rate components &gt; 0; valid status/platform/track kinds; bounded progress and scores with one documented scale.</li><li>Index foreign keys used in reads; projects(owner_id, updated_at DESC), jobs(project_id, created_at DESC), clips(job_id, ordinal), timeline_items(track_id, timeline_start_ms), transcript_words(segment_id, ordinal).</li><li>Cross-project references must be rejected: verify asset, job, clip and draft ownership in each transaction, or strengthen with composite tenant keys. A simple FK alone does not enforce common project ownership.</li><li>Cascade dependent metadata deliberately; restrict deletion of referenced media. Remove physical files only after committed metadata changes and a reference check. Decide retention before implementing deletes.</li><li>Draft saves use UPDATE ... WHERE id = :id AND version = :expected_version, incrementing version. Reject stale saves. Render an immutable snapshot so later edits cannot change an in-flight export.</li></ul>
 <h2>Queries correspond to user actions</h2><ol><li>Projects page: SELECT projects WHERE owner_id = verified Clerk subject ORDER BY updated_at DESC. Never accept ownership from a browser user_id.</li><li>Open project: authorize project, load source assets, jobs, clips and outputs, then saved_clips. Use pagination for growing history.</li><li>Generate clips: INSERT job and source reference; write job_steps; INSERT selected clips, output assets and clip_outputs when successful.</li><li>Save clip: authorize output and project; INSERT saved_clips ON CONFLICT DO NOTHING.</li><li>Open editor: authorize draft; load tracks, items, effects, cues and words in stable order. Save the composition in one version-checked transaction.</li><li>Download: authorize through project → output → media_asset, then stream local file or issue a short-lived S3 URL.</li><li>Research: read research_run and its ranked sources, retaining retrieval time because external metrics change.</li></ol>
 <h2>Scope decisions before SQL migrations</h2><p>This covers the repository’s implemented flow and its documented editor/social roadmap. It is not a claim to cover every possible future feature. Collaboration would add memberships/invitations; billing would add subscriptions/usage; full undo would add revisions; chat would add conversations/messages; provider attribution may add asset licenses. Decide whether those features belong before counting them.</p>
 <p>Suggested drawing order: users → projects → assets → jobs → clips/outputs → saved clips; then speech/research; then editing; finally optional publishing. Validate with one real example: one user, one project, one upload, one job, four clips, two caption variants, one saved output, one draft and one export.</p>
 <footer style={{color:t.text.secondary,marginTop:24}}>Evidence: DATABASE.md; migrations/001_metadata.sql; metadata_store.py; integration.py; app1.py; INTEGRATION.md; schema.sql; legacy app.py. This atlas proposes a future relational structure; it does not migrate the current records table.</footer>
 </main>;
}


export default function DatabaseChart(){
 const t=useHostTheme(); const [section,setSection]=useState(0);const [selected,setSelected]=useState('projects');
 const all=groups.flatMap((g,i)=>(g[2] as string[][]).map(r=>({r,i})));
 const lanes=[
 [['users','projects','jobs','clips','clip_outputs','saved_clips'],['user_preferences','user_platform_preferences'],['media_assets','transcripts','transcript_segments','transcript_words'],['job_steps','research_runs','research_sources']],
 [['projects','edit_drafts','timeline_tracks','timeline_items','item_effects','effect_keyframes'],['caption_styles','caption_cues','caption_words'],['exports','media_assets']],
 [['users','social_connections','publications'],['projects','social_posts','social_post_parts']]
 ];
 const edgeSets=[
 [['users','projects'],['users','user_preferences'],['users','user_platform_preferences'],['projects','jobs'],['projects','media_assets'],['jobs','clips'],['clips','clip_outputs'],['clip_outputs','saved_clips'],['media_assets','transcripts'],['transcripts','transcript_segments'],['transcript_segments','transcript_words'],['jobs','job_steps'],['jobs','research_runs'],['research_runs','research_sources']],
 [['projects','edit_drafts'],['edit_drafts','timeline_tracks'],['timeline_tracks','timeline_items'],['timeline_items','item_effects'],['item_effects','effect_keyframes'],['timeline_tracks','caption_cues'],['caption_styles','caption_cues'],['caption_cues','caption_words'],['edit_drafts','exports'],['exports','media_assets']],
 [['users','social_connections'],['social_connections','publications'],['projects','social_posts'],['social_posts','social_post_parts'],['social_posts','publications']]
 ];
 const rows=lanes[section];const nodes=rows.flatMap((lane,c)=>lane.map((name,r)=>({name,x:40+c*390,y:50+r*230})));
 const active=all.find(n=>n.r[0]===selected)!;
 const color=(i:number)=>t.chart.sequence[i%t.chart.sequence.length];
 return <main style={{padding:24,background:t.bg.editor,color:t.text.primary,fontFamily:'system-ui',lineHeight:1.5}}>
 <h1 style={{fontSize:24}}>Cascade database chart</h1>
 <p>Boxes = tables · arrows = relationships · click any box to see every field.</p>
 <div style={{display:'flex',gap:12}}>{['Core · 15 tables','Editor · +9 planned','Social · +4 optional'].map((s,i)=><button key={s} onClick={()=>setSection(i)} style={{padding:10,background:section===i?t.accent.primary:t.fill.tertiary,color:section===i?t.text.onAccent:t.text.primary,border:`1px solid ${t.stroke.primary}`}}>{s}</button>)}</div>
 <p>{groups.map((g,i)=><span key={i} style={{color:color(i),marginRight:20}}>■ {g[0] as string}</span>)}</p>
 <div style={{display:'grid',gridTemplateColumns:'minmax(0,1fr) 300px',gap:20}}>
 <div style={{overflow:'auto',maxHeight:'76vh',border:`1px solid ${t.stroke.primary}`}}>
 <svg width={rows.length*390*0.8} height={1450*0.8} viewBox={`0 0 ${rows.length*390} 1450`} role="img" aria-label="Database table relationship diagram">
 <defs><marker id="arr" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill={t.text.secondary}/></marker></defs>
 {edgeSets[section].map(([a,b])=>{const n=nodes.find(n=>n.name===a)!,m=nodes.find(n=>n.name===b)!;const vertical=n.x===m.x;const x1=vertical?n.x+160:m.x>n.x?n.x+320:n.x;const y1=vertical?n.y+158:n.y+80;const x2=vertical?m.x+160:m.x>n.x?m.x:m.x+320;const y2=vertical?m.y:m.y+80;return <g key={a+b}><path d={`M${x1} ${y1} L${x2} ${y2}`} stroke={t.text.secondary} strokeWidth="2" fill="none" markerEnd="url(#arr)"/><text x={(x1+x2)/2+5} y={(y1+y2)/2-8} fill={t.text.primary} fontSize="14" style={{paintOrder:'stroke',stroke:t.bg.editor,strokeWidth:5}}>{a==='users'&&b==='user_preferences'?'1 : 0..1':a==='jobs'&&b==='research_runs'?'1 : 0..1':a==='exports'?'N : 0..1':'1 : N'}</text></g>;})}
 {nodes.map(n=>{const data=all.find(x=>x.r[0]===n.name)!;return <g key={n.name} transform={`translate(${n.x},${n.y})`} onClick={()=>setSelected(n.name)} role="button" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter')setSelected(n.name);}} style={{cursor:'pointer'}}><rect width="320" height="158" rx="5" fill={t.bg.editor} stroke={selected===n.name?t.accent.primary:t.stroke.primary} strokeWidth={selected===n.name?3:1}/><rect width="7" height="158" fill={color(data.i)}/><text x="18" y="30" fontSize="20" fontWeight="bold" fill={color(data.i)}>{n.name}</text>{data.r[2].split('|').slice(0,3).map((f,i)=><text key={f} x="18" y={60+i*23} fontSize="13" fill={t.text.primary} fontFamily="monospace">{f.length>36?f.slice(0,33)+'…':f}</text>)}<text x="18" y="142" fontSize="13" fill={t.text.secondary}>{data.r[2].split('|').length} fields · click to unpack</text></g>;})}
 </svg></div>
 <aside style={{borderLeft:`3px solid ${color(active.i)}`,paddingLeft:16}}><h2 style={{fontSize:20}}>{active.r[0]}</h2><p>{active.r[1]}</p>{active.r[2].split('|').map(f=><div key={f} style={{fontFamily:'monospace',fontSize:13,padding:'6px 0',borderBottom:`1px solid ${t.stroke.secondary}`,overflowWrap:'anywhere'}}>{f}</div>)}<p>PK = row identity<br/>FK = reference to another table<br/>? = optional field<br/>1 : N = one to many</p></aside>
 </div>
 <h2 style={{fontSize:20}}>Where the chart stops</h2><p>User → Project → Video → Transcript → Segment → Word → [text, start time, end time]. Those final values are fields, not additional tables.</p>
 <p>Draw each group on a separate sheet with matching colors. Underline PKs, circle FKs, and label arrows 1/N. Use a cylinder for local/S3 file storage.</p>
 <details><summary>All additional cross-links and design details</summary><p>The diagram emphasizes the main relationships. Foreign keys in the field panel show additional links, including source files, job lineage, project bookmarks and output media.</p><DatabaseAtlasDetails/></details>
 <p style={{color:t.text.secondary,fontSize:13}}>Proposed design: 15 core + 9 editor + 4 optional social tables. Repeated context boxes do not add tables. Current active storage remains one JSONB table and four views; no migration or live database inspection was performed.</p>
 </main>;
}
