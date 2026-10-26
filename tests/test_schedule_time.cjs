const assert=require('node:assert/strict');
global.window={};require('../web/post_schedule.js');const t=window.CascadeScheduleTime;
assert.deepEqual(t.candidates('2026-10-30T15:30','America/Chicago').map(c=>new Date(c.instant).toISOString()),['2026-10-30T20:30:00.000Z']);
assert.equal(t.candidates('2027-03-14T02:30','America/Chicago').length,0);
assert.deepEqual(t.candidates('2026-11-01T01:30','America/Chicago').map(c=>c.offset),[-300,-360]);
assert.deepEqual(t.candidates('2026-11-01T01:30','America/Chicago').map(c=>new Date(c.instant).toISOString()),['2026-11-01T06:30:00.000Z','2026-11-01T07:30:00.000Z']);
assert.equal(new Date(t.candidates('2026-12-30T15:30','Asia/Kathmandu')[0].instant).toISOString(),'2026-12-30T09:45:00.000Z');
assert.equal(t.date(Date.parse('2026-10-30T01:00:00Z'),'America/Chicago'),'2026-10-29');
console.log('PASS: JS timezone conversion, DST gap/fold, fractional offset and date boundary');
