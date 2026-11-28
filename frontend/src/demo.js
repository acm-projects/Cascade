// Demo mode (demo_final branch): the presentation-night hike demo. The server recognises the same recordings.
export const DEMO_RECORDINGS = new Set([
  "IMG_0158.mov",
  "Video_1074791232_DJI_20261125102501_0013_D_MP4_56828872_6000_2026112510250_video_original.MP4",
  "Video_1074791296_DJI_20261125102550_0014_D_MP4_1016579242_119000_20261125102550_video_original.MP4",
  "Video_1074791424_DJI_20261125102835_0016_D_MP4_195198087_22000_20261125102834_video_original.mov",
  "Video_1074791488_DJI_20261125102906_0017_D_MP4_7981198553_940000_2026112510296_video_original.MP4",
  "Video_1074791552_DJI_20261125104707_0018_D_MP4_6466740034_761000_2026112510476_video_original.MP4",
  "Video_1074791872_DJI_20261125110028_0023_D_MP4_3198071390_377000_2026112511028_video_original.MP4",
  "Video_1074791936_DJI_20261125110709_0024_D_MP4_443170651_52000_202611251178_video_original.MP4",
  "Video_1074792000_DJI_20261125110821_0025_D_MP4_103912127_12000_2026112511820_video_original.MP4",
  "IMG_6227.MOV",
  "IMG_6228.MOV",
  "IMG_6229.MOV",
  "IMG_6230.MOV",
  "IMG_6231.MOV",
  "IMG_6232.MOV",
  "IMG_6233.MOV",
  "Video_1074791040_DJI_20261125102035_0010_D_MP4_62719618_7000_20261125102034_video_original.MP4",
  "Video_1074791104_DJI_20261125102240_0011_D_MP4_71868583_8000_20261125102240_video_original.MP4",
  "Video_1074791296_DJI_20261125102550_0014_D_MP4_1016579242_119000_20261125102550_video_original.mov",
  "Video_1074791360_DJI_20261125102815_0015_D_MP4_133962978_15000_20261125102814_video_original.MP4",
  "first.MP4",
  "second.MOV"
]);

/** Two or more files, all of them the hike recordings */
export function isDemoFiles(files) {
  const list = Array.from(files || []);
  return list.length >= 2 && list.every((file) => DEMO_RECORDINGS.has(file.name));
}

// The prompts typed on stage: they fill the box when it is clicked
export const DEMO_FIND_PROMPT = "Find short clips from our hike that capture our funniest and sweetest moments as friends. Look for candid reactions, playful group moments, and little details that make the day feel nostalgic.";
export const DEMO_BRANCH_PROMPT = "I love this one! Find more fun moments like it from our hike.";
export const DEMO_EDIT_PROMPT = "Make a 15-second edit of our hike to the reference's sound. Type POV hike with cascade on crumpled paper while we chant one, two, three, Cascade, tear the paper into CASCADE being written on the rock on the beat, flash each of our faces, then the top of the waterfall, our wave, the four-box collage and our funniest moments, and end on the hug scrunching back into the paper.";
export const DEMO_SONG = "Alive Again";

// The post copy on Export for the demo edit
export const DEMO_POST = {
  name: "A Break to Touch Grass",
  caption: "Taking a break from presentation prep with Cascade. We\u2019re not sure where we are, but we\u2019re out here touching grass and reconnecting with nature. \ud83c\udf3f",
  hashtags: ["#Hiking", "#TouchGrass", "#NatureBreak", "#ReconnectWithNature", "#OutdoorTime", "#PresentationPrep"],
};
