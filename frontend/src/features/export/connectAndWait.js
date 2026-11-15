// One-button "connect, then publish": opens the provider's sign-in in a new window, then checks every couple of
// seconds until the server says the account is connected, and returns that connection.
//   connect() -> { url }          starts sign-in (api.connectYoutube / api.connectLinkedin)
//   check()   -> { connected, ... }
// The window is opened before anything is awaited, so browsers (Safari especially) don't block it as a pop-up.
const CHECK_MS = 2500;
const GIVE_UP_MS = 5 * 60 * 1000;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function connectAndWait({ connect, check, name }) {
  const popup = window.open("about:blank", "_blank");
  if (!popup) throw new Error(`Allow pop-ups for Cascade, then try ${name} again.`);
  try {
    const { url } = await connect();
    popup.location.href = url;
  } catch (err) {
    popup.close();
    throw err;
  }
  const deadline = Date.now() + GIVE_UP_MS;
  while (Date.now() < deadline) {
    await wait(CHECK_MS);
    const closed = popup.closed;
    const connection = await check().catch(() => null);
    if (connection?.connected) {
      if (!popup.closed) popup.close();
      return connection;
    }
    if (closed) throw new Error(`The ${name} sign-in window was closed before connecting.`);
  }
  throw new Error(`${name} sign-in took too long. Try again.`);
}
