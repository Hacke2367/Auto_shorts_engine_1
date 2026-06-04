# AutoShorts Agentic Pipeline - Quick Command Guide[cite: 4]

## Scenario 1: Naya khali project/folder banana ho[cite: 4]
* Jab bhi naya video start karna ho, sabse pehle ye command chalega ek naya folder banane ke liye.[cite: 4]
* **Command:** `python -m src.cli.autoshorts new --template bar_chart`[cite: 4]

## Scenario 2: AI se naye topic ideas dhoondhne ho[cite: 4]
* Agar aap chahte hain ki AI internet se trend check karke khud ideas laye.[cite: 4]
* **Command:** `python -m src.cli.autoshorts phase1-discover --template bar_chart`[cite: 4]

## Scenario 3: AI ke laye hue ideas mein se kisi ek topic ko final/approve karna ho[cite: 4]
* Jo list AI ne di, usme se ek number chunna ho.[cite: 4]
* **Command:** `python -m src.cli.autoshorts phase1-approve --job jobs/auto/my_job --index 2 --template bar_chart`[cite: 4]

## Scenario 4: Apna khud ka specific topic dekar seedha data nikalna ho (Discovery skip karke)[cite: 4]
* Jab aapko topic pehle se pata ho aur seedha internet se uska CSV data nikalna ho.[cite: 4]
* **Command:** `python -m src.cli.autoshorts phase1-extract --job jobs/auto/my_job --template bar_chart --topic "Top 5 AI Companies by Revenue 2024"`[cite: 4]

## Scenario 5: Sirf script generate karni ho[cite: 4]
* Data aa chuka hai aur sirf ek specific style (jaise roast ya analyst) mein script likhwani ho.[cite: 4]
* **Command:** `python -m src.cli.autoshorts phase2 --job jobs/auto/my_job --persona savage_roast_master`[cite: 4]

## Scenario 6: Script chhoti padh gayi ho aur UnderRunError aa jaye (Fix/Repair karna ho)[cite: 4]
* Agar audio itni chhoti ban gayi ki template render nahi ho pa raha, toh ye command script ko bada karega aur error theek karega.[cite: 4]
* **Command:** `python -m src.cli.autoshorts repair --job jobs/auto/my_job --persona savage_roast_master --template bar_chart --max-tries 3`[cite: 4]

## Scenario 7: Data nikalne ke baad (Phase 2 se 4 tak) pura video ek sath banana ho (Online/Real API)[cite: 4]
* Jab data ready ho aur aap chahte ho ki system khud script likhe, ElevenLabs se aawaz banaye, aur Manim se video render kar de.[cite: 4]
* **Command:** `python -m src.cli.autoshorts run --job jobs/auto/my_job --template bar_chart --persona savage_roast_master --voice-id JBFqnCBsd6RMkjVDRZzb --model-id eleven_multilingual_v2 -q h`[cite: 4]

## Scenario 8: Pura video ek sath banana ho lekin API ka paisa bachana ho (Testing / Offline mode)[cite: 4]
* Jab aap system test kar rahe ho aur chahte ho ki dummy audio use ho taaki ElevenLabs API waste na ho.[cite: 4]
* **Command:** `python -m src.cli.autoshorts run --job jobs/auto/my_job --template bar_chart --persona savage_roast_master --offline -q h`[cite: 4]

## Scenario 9: Sirf Video render karni ho[cite: 4]
* Jab `job.json` aur audio files already folder mein padi hon, aur sirf Manim ka visual engine chalana ho.[cite: 4]
* **Command:** `python -m src.cli.autoshorts render --job jobs/auto/my_job -q h`[cite: 4]

## Scenario 10: State file ka error aaye (Pichla phase rerun na ho raha ho)[cite: 4]
* Agar system soche ki step pehle hi ho chuka hai, toh us job folder mein jake ek hidden file hoti hai usko manually theek karna padta hai.[cite: 4]
* **Action:** `jobs/auto/my_job/.pipeline_state.json` file ko kholo aur jo step dubara chalana hai, usko wahan se delete kar do ya `true` ko hata do.[cite: 4]