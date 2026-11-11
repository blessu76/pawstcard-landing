Effective date: [confirm: effective date, set when published] · Version v0.1 (draft)

Pawstcard (“the app”, “we”) is a mobile app that helps independent pet sitters turn their photos and a few taps into a short visit report (a “Pawstcard”) that they can send to the pet's owner. This policy explains what the app handles, why, and how you can control it. It follows applicable law, including Korea's Personal Information Protection Act.

**The short version**: your visits, clients and pets are stored **on your phone**. There is no account to create, but the app signs you in **anonymously** to Firebase (Google) so it can upload. When you generate a report, the **photos and facts of that visit are sent to Google's AI** (Firebase AI Logic / Vertex AI). When you **send** a Pawstcard, a web page containing it (names, photos, text, and a walking-route map if you recorded one) is uploaded to Google Firebase Storage and anyone who has the link can open it. The app records walks only **while it is open on screen**. We use Google Firebase Analytics to count app usage; it does not receive names, photos or locations. We do not sell personal information.

## 1. Who is responsible

| Item | Detail |
|---|---|
| Operator | Davy Kim (ipe Studio), Seoul — an individual developer, not yet registered as a business. Once registered, the trade name, registration number etc. will be added to this table.  |
| Privacy officer | Davy Kim, Representative · privacy@ipe.rest `[confirm P1: the app's own support address in code is a personal Gmail address (lib/features/settings/about_screen.dart `supportEmail`); change the app to privacy@ipe.rest or confirm which address is published]`  |
| Address / phone | `[confirm P2: whether to show an address/phone — store and e-commerce-law duty; email-only if permitted]` |

## 2. Where this policy applies

- **The Pawstcard mobile app** for iOS and Android (bundle `rest.ipe.pawstcard`).
- **Pawstcard pages created by the app** (the web page behind a link you send), because they carry the data described in section 3.
- The Pawstcard **website** (pawstcard.ipe.rest — landing page, journal, waitlist) is covered by its own website policy, not by this document.
- When you use the app for your clients, **you** choose what to enter about your clients (pet owners) and their pets. Please enter only what you need and tell your clients that you use Pawstcard `[confirm P3: role split — whether the sitter is the controller and we are a processor for client data; legal check]`.

## 3. What we collect, why, and how long

| Category | Data | Purpose | Where it lives / who receives it | Retention |
|---|---|---|---|---|
| Your work data (on device) | client name and contact (phone/email, used only to pre-fill the share sheet), pet name, species/breed, personality traits, special instructions, visit type and times, tapped “facts” (feeding, water, poop scale, walk minutes, play, mood…), medication names and times, report text, your name for the sign-off, settings, a monthly AI-call counter  | provide the app | local database (SQLite) on your phone only; not uploaded as such | until you delete the item, delete the app, or restore a backup over it |
| Photos | photos you take or pick, **resized to 1024 px and re-encoded as JPEG with all metadata (including GPS) removed**; the original stays in your own camera roll  | show in the report, give to the AI | resized copy stored on your phone; copies leave the phone as described below | on device until you delete them or the app |
| AI report text | the photos and visit information listed in section 6 are sent to Google's Gemini model (via Firebase AI Logic, Vertex AI backend, model `gemini-2.5-flash-lite`); the text it returns is stored on your phone  | write the draft report you then review and approve | Google (see section 6) | per Google's terms `[confirm P4: Vertex AI data handling — retention, abuse-monitoring logs, no training on your data; region]` |
| Sent Pawstcard (web page) | when you tap send: one self-contained HTML page with your report text, the pet's and owner's names, the sitter name, visit times, photos (embedded), the medication line, and a route map image if you recorded a walk; plus one preview photo (JPG)  | let the pet's owner open the report by link | **Google Firebase Storage** (project `pawstcard-65d51`). Stored under a random name, `snapshots/<your anonymous user id>/<random id>.html` and `photos/<your anonymous user id>/<random id>.jpg`. **Anyone who has the link can open it; the page cannot be listed or searched.**  | `[confirm P5: retention — nothing in code deletes these files; decide a period and a deletion procedure (see section 7)]` |
| Anonymous sign-in | an anonymous Firebase Authentication user id, created the first time you send a report; **no email, name or password**  | satisfy Storage access rules and keep your uploads under your own folder | Google Firebase Authentication | until deleted `[confirm P6: how and when anonymous users are deleted]` |
| Walk route (optional) | GPS points collected **only while the app is open and you have started a walk**; points are turned into one route line and sent to Google Maps Static Maps to draw a map picture, which is embedded in the Pawstcard  | draw the walking route in the report | Google Maps Platform (route coordinates, up to 100 points); the map picture is then part of the sent page | route points: on device while you work; map picture: as the sent page above `[confirm P7: whether Google retains Static Maps request data]` |
| Weather (optional) | approximate position (latitude/longitude) at the time of a visit, to look up the weather  | add weather to the report | Open-Meteo (weather API) receives the coordinates in the request | not stored by us `[confirm P8: Open-Meteo operator, country, its terms for use in a paid commercial app (its free tier is for non-commercial use), and its retention]` |
| Calendar (optional) | one event per scheduled visit written to a calendar you choose; **the app never reads your calendar events**  | show your visits in your own calendar | your device calendar; if that calendar syncs to iCloud/Google, that provider also holds the event | until you delete the visit/client or the event |
| Usage statistics | anonymous app events: eight kinds, such as report generated, report sent, photo added, walk recorded; **no names, no photos, no text, no coordinates, no links**  plus the standard data Firebase Analytics collects automatically (app instance id, device/OS model, app version, country-level location from IP, session data) `[confirm P9: Firebase Analytics settings — event retention, Google signals off, advertising-ID collection off]` | understand which features are used | Google Firebase Analytics (Google Analytics 4) | per Google Analytics retention setting `[confirm P9]` |
| Backup file | a `.pcbak` file you export yourself (all your data and resized photos, zipped); you decide where it goes through the system share sheet  | move or keep your data | wherever you save or send it (Files, iCloud, Mail…) | until you delete the file |
| Messages you send us | your email address and what you write | reply to your request | our mailbox | `[confirm P10: retention, e.g. 1 year after resolution]`; deleted on request |

**What we do not collect**: names, phone numbers or passwords of yours as an account (there is no account), contacts, your calendar contents, background location, or advertising identifiers by design `[confirm P9]`. There is no in-app purchase SDK in the current version.

## 4. Device permissions

| Permission | When the app asks | What it is used for |
|---|---|---|
| Camera | when you choose to take a photo | take visit photos  |
| Photo library | when you choose photos | pick existing photos  |
| Location, **while using the app** | when you start a walk or the app looks up the weather | draw the walking route; find the weather. **The app does not track you in the background.**  `[confirm P11: the iOS file also declares an “Always” location purpose string although the code uses only when-in-use; decide whether to remove it, see store-gap G-03]` |
| Calendar | only when you switch on the calendar option in Settings | add your visits to a calendar you choose (add/change/remove only)  |

You can change or withdraw these permissions in your phone's settings; the related feature then stops working (you can still write reports without photos from the camera, a route, weather or calendar).

## 5. Cookies, analytics and advertising

1. **No advertising.** The app contains no advertising SDK.
2. **Firebase Analytics** (Google Analytics 4) counts anonymous usage events as in section 3. The app does not show a consent screen or an off switch for analytics today `[confirm P12: whether to add an in-app analytics choice, and whether consent is needed for users in the EEA, UK and Switzerland; Korean users]`.
3. **Shared Pawstcard pages** contain no scripts and load nothing from other sites: they are a single page with inline styles and embedded images, and block scripts.

## 6. Sharing with third parties; processors; transfers abroad

We do not sell personal information. We provide it to third parties only as below, and where the law requires. Only providers we actually use are listed.

| Recipient | What / purpose | Data | When / how | Country | Retention | Recipient contact |
|---|---|---|---|---|---|---|
| Google LLC — Firebase AI Logic / Vertex AI (Gemini) | write the draft report | the visit photos (resized JPEG), the tapped facts, the pet's name and species/breed, personality traits and special instructions, your sign-off name and the owner's name as they appear in the prompt `[confirm P13: exact prompt fields — re-check report_writer.dart before publishing]`. **Medication names and times are not sent.**  | when you tap generate; up to three attempts per request | US and others `[confirm P4: region]` | `[confirm P4]` | contact given at policies.google.com/privacy |
| Google LLC — Firebase Storage and Firebase Authentication | host the page you send; anonymous sign-in | the sent page and preview photo; anonymous user id | when you tap send | US and others `[confirm P14: Storage bucket region]` | `[confirm P5, P6]` | policies.google.com/privacy |
| Google LLC — Google Maps Platform (Static Maps) | draw the route picture | route coordinates (up to 100 points) in the request | when you send a report that has a recorded walk | US and others | `[confirm P7]` | policies.google.com/privacy |
| Google LLC — Firebase Analytics | usage statistics | events in section 3 and standard automatic data | while the app is used | US and others | `[confirm P9]` | policies.google.com/privacy |
| Open-Meteo | weather | latitude/longitude | when the app looks up weather | `[confirm P8: country]` | `[confirm P8]` | `[confirm P8: contact]` |
| The person you send the link to (usually the pet's owner) and anyone they forward it to | read the report | the sent page (section 3) | when you share the link | — | until deleted (section 7) | — |
| Apple Inc. / Google LLC (stores) | app distribution; crash and usage reporting under their own terms | per their policies | — | US and others | per store policy | apple.com/legal/privacy · policies.google.com/privacy |

**How to refuse the transfer, and the procedure** `[confirm P15: wording to be finalised by legal review]`
- Method: do not tap generate (write the report yourself), do not record a walk (no map data), do not tap send (nothing is uploaded), deny the location permission (no weather or route). Analytics cannot yet be switched off in the app (see P12).
- Procedure: apply the method yourself, or ask at privacy@ipe.rest.
- If you refuse: that function (AI draft, route map, weather, sending a link) is unavailable. Transfers essential to the app itself (for example anonymous sign-in for sending) cannot be refused; in that case please stop using that feature.

## 7. Deletion, and how to ask us to delete

- **On your phone**: deleting a client deletes its pets, visits, photos and reports from the app, and the calendar events the app created for them; deleting a pet deletes its visits. Deleting the app deletes all local data.
- **Pawstcards you already sent**: deleting something in the app **does not remove the web page or photo already uploaded** — the app has no function that deletes uploaded files, and the storage rules do not allow the app to delete them.  **To remove a sent page, write to privacy@ipe.rest from the address you use, with the link; we will delete it `[confirm P16: deletion procedure and time — we can find files only by link or by the anonymous user id; decide who deletes them, how requests are verified, and the response time]`.** `[confirm P17: the product requirement says a sitter can invalidate a link by deleting a report; the code does not do this yet — build it or change the wording]`
- **Account**: there is no account to close. To delete your anonymous sign-in and everything uploaded under it, write to privacy@ipe.rest `[confirm P6, P18: Apple Guideline 5.1.1(v) account deletion — decide whether an in-app deletion path is required; store-gap G-02]`.
- **Analytics data** is not tied to your name; we cannot locate an individual's records in it `[confirm P12: legal check]`.
- Data we keep because the law requires it is kept for the statutory period `[confirm P19: whether this applies]`.

## 8. Your rights

You may at any time request access, correction, deletion or suspension of processing, and withdraw consent.
- **How to ask**: privacy@ipe.rest; we tell you the outcome within 10 days (same as ipe() common policy).
- **Representatives**: a legal guardian or authorised representative may make the request, and we may ask for proof of authority `[confirm P20: how we verify]`.
- **If we decline**: we tell you the reason and how to object.
- **Pet owners (your clients)**: if a pet owner asks about a report you sent, they can write to us at the same address, and we will ask you or delete the page as in section 7.
- **Objection**: if you disagree with the outcome you may ask again at the same address and apply for relief to the bodies in section 11.
- If you are in the EEA, UK or Switzerland you also have GDPR rights (objection, portability, complaint to a supervisory authority).

## 9. Children

Pawstcard is a tool for adult pet-sitting professionals and is not directed to children. We do not knowingly collect personal information from children under 14 in Korea (under 13 in the US; or the age your country sets in the EU, 13–16). If we learn we have, we delete it promptly. The app has no way for a child to be addressed by us: clients' names entered by the sitter may belong to a household that includes minors, which is why section 2 asks you to enter only what is needed. `[confirm P21: minimum age (e.g. 18/16), App Store age rating, and whether to apply for Google Play “Designed for Families” — do not apply before deciding]`

## 10. Security

We design the app to keep your work on your phone and to upload only what you send. Measures below `[confirm P22: legal review — which measures under the Enforcement Decree apply]`.

| Measure | Status |
|---|---|
| Transit encryption | Firebase and Google APIs are reached over HTTPS `[unverified: not tested by us; standard for these SDKs]` |
| Uploaded pages | random file names; no listing; only the owner (anonymous user) can read the file through the app's rules; the link token opens it for anyone holding it  |
| Photos | resized, all metadata removed before upload  |
| Medication data | never sent to the AI  |
| Firebase App Check | `[confirm P23: whether enabled in the Firebase console — code comments say AI Logic is protected by App Check; [unverified]]` |
| Own servers | none. The only personal data we hold ourselves is mail correspondence |
| Access to our mailbox | one person (the privacy officer) `[confirm P24: two-step verification in place]` |

## 11. Complaints

KISA Privacy Infringement Report Center (privacy.kisa.or.kr, 118), Personal Information Dispute Mediation Committee (kopico.go.kr, 1833-6972), Supreme Prosecutors' Office (spo.go.kr, 1301), National Police Agency Cyber Bureau (ecrm.police.go.kr, 182).

## 12. Changes

If this policy changes, we announce it at the address where it is published (and the canonical address https://ipe.rest/legal) and in the app 7 days before it takes effect; for changes that disadvantage you or materially affect your rights we give 30 days' notice. Past versions are available on request (privacy@ipe.rest). `[confirm P25: the final URL of this policy — see store-gap G-01]`
