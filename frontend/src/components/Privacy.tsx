import { BASE } from "../env";
import Logo from "./Logo";
import ResponsibleGaming from "./ResponsibleGaming";
import ThemeToggle from "./ThemeToggle";

const UPDATED = "November 2, 2026";
const CONTACT = "joshd.haber@gmail.com";

/** /privacy: what the site keeps, where it goes and how to delete it. Linked from the footer, the sign-in sheet and Google's
 *  sign-in screen. Keep it true to the code: app/auth.py (accounts), prefs.ts and BetSlipContext (browser storage), geoState.ts. */
export default function Privacy() {
  return (
    <div className="wrap">
      <header>
        <div>
          <h1><Logo /> The Haber <span className="grad">Process</span></h1>
          <div className="sub"><a href={BASE}>← Back to the site</a></div>
        </div>
        <div className="head-actions"><ThemeToggle /></div>
      </header>

      <article className="legal">
        <h2 className="page-h">Privacy policy</h2>
        <p className="mut">Last updated {UPDATED}</p>

        <p>
          The Haber Process (process.jdhaber.com) is a personal project by JD Haber that projects player stats and prices them against sportsbook
          lines. You can use every part of it without an account. This page explains what it keeps about you, why and how to remove it.
          The short version: it keeps only what it needs to sign you in and remember your settings, it doesn't run ads or analytics, and it
          never sells or shares your information.
        </p>

        <h3>If you create an account</h3>
        <p>Signing in is optional. When you sign in with Google or with a link sent to your email, the site stores:</p>
        <ul>
          <li><b>Your email address</b>, which identifies your account.</li>
          <li><b>From Google, if you use it:</b> your name, a link to your profile photo and Google's ID for your account. The site asks Google
            only for your basic profile and email (the <code>openid</code>, <code>email</code> and <code>profile</code> scopes). It can't see
            your Gmail, contacts, files or anything else in your Google account.</li>
          <li><b>That you confirmed you're 21 or older</b>, and when.</li>
          <li><b>Your preferences:</b> theme, default sportsbook and how Best props are shown.</li>
          <li><b>Your teams and favorite players</b>, used to put your teams' games first and list your players on the compare page.</li>
          <li><b>Bets you track</b> on My bets: the sportsbook, stake, odds and each leg (player, market, line), when you tracked
            it and how it settled. They're used only to grade your bets and show your record, and no one else can see them.</li>
          <li><b>Your betslip:</b> its picks and the stake at each sportsbook, so the same slip is there on every device you sign in on.
            The state you're betting from stays on each device.</li>
          <li><b>When you created the account and last signed in.</b></li>
          <li><b>Your signed-in sessions:</b> one per browser, with the browser's name and version (its "user agent") and when it was last
            used. The cookie that keeps you signed in is stored only as a one-way hash, and it expires after 30 days without use.</li>
          <li><b>Sign-in emails:</b> when you ask for a link, the site keeps your address and a hashed copy of the link and code for 15 minutes
            (plus a day before they're cleared), so they can be used once.</li>
        </ul>
        <p>No passwords are stored. There aren't any.</p>

        <h3>Stored in your browser</h3>
        <p>
          With or without an account, the site remembers some things in your browser's own storage so they're still there next time: your theme,
          league, sportsbook and Best props settings, your betslip (its picks, stakes and the state you're betting from) and a few display
          choices. They stay on your device (except the betslip's picks and stakes, saved to your account while you're signed in, as
          above), and are cleared when you clear your browser's site data. The only cookie is
          the sign-in cookie above. There are no tracking or advertising cookies.
        </p>

        <h3>Your location</h3>
        <p>
          Some sportsbooks' links need to know which state you're in. If you allow it, the betslip asks your browser for your location and works
          out the state <b>on your device</b>, against a map built into the page. Your location is never sent to the site or anyone else. Only the
          state is remembered, with your betslip, in your browser.
        </p>

        <h3>Services the site uses</h3>
        <ul>
          <li><b>Railway</b> hosts the site and its database. Like any web server, it logs requests (your IP address, the page and the time) for
            troubleshooting, and the site briefly keeps IP addresses in memory to rate-limit sign-in attempts.</li>
          <li><b>Google</b> handles "Continue with Google" when you choose it, under <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google's privacy policy</a>.</li>
          <li><b>Resend</b> delivers sign-in emails, so it receives your email address and the message.</li>
          <li><b>Bet slip screenshots:</b> when you upload one on My bets, your device reads its text and sends only that text here to fill
            in the bet for you to check; the image stays on your device and the text isn't kept. The reader's code and English language data
            load from <b>jsDelivr</b> the first time. If the site is set up to have <b>Anthropic</b>'s Claude read slips instead, the image is
            sent to Anthropic's API and isn't kept by this site; under Anthropic's API terms it isn't used to train models (see
            {" "}<a href="https://www.anthropic.com/legal/privacy" target="_blank" rel="noopener noreferrer">Anthropic's privacy policy</a>).</li>
          <li><b>Google Fonts</b> serves the site's typeface, and <b>ESPN</b> serves team logos and player photos. Your browser loads these from
            their servers, which see your IP address the way any website does.</li>
          <li><b>Sportsbooks:</b> buttons like "Place bet" open the sportsbook's own site. What happens there is up to that sportsbook and its
            privacy policy. The Haber Process never places bets and never sees your sportsbook account.</li>
        </ul>
        <p>Nothing about you is sold, rented or shared for advertising.</p>

        <h3>Deleting your information</h3>
        <p>
          Signed in, open <b>Preferences</b> from the account menu and choose <b>Delete account</b>. That immediately deletes your account, its
          preferences, your tracked bets, your saved betslip, every signed-in session and any unused sign-in links. You can also delete a single tracked
          bet from My bets. You can also sign out at any time, which deletes that session. To
          clear what's stored in your browser, clear this site's data in your browser settings. If you'd rather ask, email <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.
        </p>

        <h3>Age</h3>
        <p>
          The site is about sports betting and is meant for people 21 and older. Accounts require confirming you're 21 or older. If you believe
          someone under 21 has created an account, email <a href={`mailto:${CONTACT}`}>{CONTACT}</a> and it will be deleted.
        </p>

        <h3>Changes and contact</h3>
        <p>
          If this policy changes, the new version will be posted here with a new date. Questions or requests: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.
        </p>
      </article>

      <footer>
        <span className="signoff">Projections and win chances, not betting advice.</span>
        <ResponsibleGaming />
      </footer>
    </div>
  );
}
