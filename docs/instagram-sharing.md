# Instagram sharing

Meta's official [iOS Sharing to Reels documentation](https://developers.facebook.com/docs/ios/sharing-to-reels-instagram) describes loading a native Reels composer using a Meta app ID, native pasteboard video data and `UIApplication` URL handling. Its [official Android sample](https://github.com/fbsamples/share_to_reels_android) likewise implements a native app integration. These do not provide Cascade's website with a URL that attaches a local MP4 or prefills a web caption. No such supported website URL was found. Some Meta documentation pages were inaccessible to the documentation tool; the official iOS documentation and Android sample were readable.

The [W3C Web Share specification](https://www.w3.org/TR/web-share/) supports passing files and text to a user-selected OS share target. It requires a secure context, permission policy access, and transient user activation. It cannot force Instagram as the target, tell whether Instagram is installed, select Feed versus Reel, confirm the target's composer loaded the file, or verify publication. A successful share promise also does not confirm caption retention or publication.

Cascade feature-detects `navigator.share`, `navigator.canShare` and `File` in a secure context, then checks the actual final MP4 with `canShare({files: [file]})`. It never relies on mobile user-agent detection. The file is prepared by reusing the preview's final export Blob (the same renderer and filename as Download), including subtitles, edits, reframing and B-roll. Preparation happens before the share click, since waiting for a render can exhaust user activation. Once ready, Share video calls the native share API synchronously from that click. If file-plus-text sharing is accepted, the current post caption and hashtags are included; otherwise the video alone is shared and the copy button remains available.

The user chooses Instagram in the sheet, then Reels if offered, and completes posting there. Copy caption & hashtags stays available even on supported devices. The compact manual Download & Open Instagram action is always accessible, including when Instagram is absent from the share sheet. Unsupported devices use it as primary. It downloads first and then opens Instagram with the instruction “Click Create and select your downloaded clip.” Browser file-picker/caption prefill is not attempted. Canceled sharing is handled neutrally, including the possibility that no target was available; it does not automatically download or open Instagram. Other share failures offer retry and manual fallback. Duplicate clicks are disabled while sharing/downloading.

## Verification and environment limits

`node tests/test_instagram_share.cjs` exercises capability profiles without browser automation:

| Test profile | Outcome | Instagram composer already loaded? |
| --- | --- | --- |
| Desktop-style: no Web Share API | Manual fallback | Not supported by this tested capability profile; no device test |
| Mobile-style: MP4 file and text accepted | Final file and caption passed to mocked share API synchronously | Not confirmed; no physical mobile browser/Instagram app available |
| Mobile-style: files accepted, text rejected | Final MP4 alone passed; copy fallback retained | Not confirmed; no physical mobile browser/Instagram app available |
| Insecure context, policy rejection, file sharing rejected | Manual fallback | Not attempted |
| Share canceled/blocked/failed | Retry/fallback message; no automatic publication claim | Not confirmed |
| Popup blocked or rendering failed | Download still works if only popup is blocked; failed rendering closes tab | Not attached by the website |

The tests verify file bytes, filename/MIME, caption versus video separation, file-only payloads, user-activation call ordering, cancellation/error messages, popup blocking and render failures. Existing backend renderer/YouTube checks are run separately. These are mocked capability tests, not desktop Safari, Android Chrome or iOS Safari device certification. Browser automation is intentionally not run for this change, per the request. To validate an actual device, open Cascade over HTTPS (or a browser-recognized local secure context), select Instagram, tap Share video, choose Instagram if offered, and inspect the received video and caption before completing or canceling the post.
