export const MAX_CLIPS = 50;
const words = {one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,
  eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,
  twenty:20,thirty:30,forty:40,fifty:50};
const number = '(?:\\d+(?:\\.\\d+)?|' + Object.keys(words).join('|') + ')(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?';
const request = new RegExp('(?:\\b(?:generate|find|create|make|return|produce|give|show|want|need|output|asked for)\\s+(?:me\\s+|of\\s+)?(?:exactly\\s+|another\\s+)?|^)(' + number + ')\\s+(?:(?:more|new|short|video|audio|funny|sad|interesting|best|emotional|action|exciting|surprising)\\s+){0,3}clips?\\b', 'gi');

export function requestedClipCount(prompt, fallback) {
  const matches = [...prompt.matchAll(request)];
  const token = matches.at(-1)?.[1]?.toLowerCase();
  const count = token ? (/^\d/.test(token) ? Number(token)
    : token.split(/[- ]/).reduce((sum, part) => sum + words[part], 0)) : Number(fallback);
  if (!Number.isInteger(count) || count < 1 || count > MAX_CLIPS) {
    throw new Error(`Choose between 1 and ${MAX_CLIPS} clips.`);
  }
  return count;
}
