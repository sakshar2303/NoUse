# Nouse Eval Results
Genererad: 2026-04-02 16:39
## Sammanfattning
| Konfiguration | Modell | Nouse | Frågor | Avg Score | Halluc | Tid/q |
|---|---|:---:|:---:|:---:|:---:|:---:|
| A — liten, ingen Nouse | `glm-4.7-flash` | — | 5 | 2.00/3 (67%) | 0 | 128.8s |
| B — liten + Nouse | `glm-4.7-flash` | ✅ | 5 | 2.40/3 (80%) | 0 | 118.0s |
| C — stor, ingen Nouse | `glm-4.7-flash` | — | 5 | 2.00/3 (67%) | 0 | 128.8s |

## Fråga-för-fråga (urval)

### q001
**glm-4.7-flash** [score=3/3]  
> Metafilosofi är en självrefererande disciplin eftersom den analyserar filosofins egna förutsättningar och metoder. Relationen till självrefererande system är att metafilosofi utgör ett sådant system d

**glm-4.7-flash +Nouse** [score=0/3]  
> 


### q004
**glm-4.7-flash** [score=0/3]  
> 

**glm-4.7-flash +Nouse** [score=3/3]  
> Kunskapsminnet innehåller relationen "FNC Framework —[stärker]→ Bisociation Engine" med en bevisvärde (ev) på 0,71, vilket indikerar att påståendet är osäkert och under granskning. Minnet ger inga spe


### q003
**glm-4.7-flash** [score=3/3]  
> Next.js använder **inte** JSON5 som standard.

Konfigurationsfiler som `package.json` och `next.config.js` använder vanlig JSON (eller JavaScript/TypeScript).

Om du refererar till JSON5 i din kod, be

**glm-4.7-flash +Nouse** [score=3/3]  
> Kunskapsminnet innehåller ingen information om Next.js. Det finns dock relationer för JSON5 kopplat till 'analyticsverktyg', 'Babel' och 'Chromium', men inget som förklarar dess koppling till Next.js.


### q005
**glm-4.7-flash** [score=2/3]  
> httpx är ett modernt, asynkront HTTP-klientbibliotek för Python. Det designades för att vara ett lättviktigt och snabbt alternativ till den vanliga `requests`-biblioteket.

Det stöder HTTP/1.1, HTTP/2

**glm-4.7-flash +Nouse** [score=3/3]  
> Enligt Nouse-minnet är **httpx** ett HTTP-bibliotek som används för att skicka HTTP POST requests.

Flera specifika användningsområden nämns i minnet:
*   För **HTTP-probing** för att kontrollera till


### q002
**glm-4.7-flash** [score=2/3]  
> Det finns ingen officiell koppling mellan IBM Cognos och MIT-licensen. Cognos Analytics är proprietär mjukvara.

Om det är fråga om en specifik, fristående projekt-repo som heter "cognos-ai" (t.ex. på

**glm-4.7-flash +Nouse** [score=3/3]  
> Enligt Nouse-kunskapsminnet finns en koppling där **cognos-ai** licensieras under **MIT License**.

Relationen är specificerad som: `cognos-ai --[licensieras_under]--> MIT License`.

*Obs: Detta är ma

