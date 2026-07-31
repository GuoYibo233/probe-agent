# CHECK_50 — 参数定位人工核对件(SEED=20260729)

定位区间用【】标出,前后各 80 字符上下文;逐条核对【】里是不是该参数该有的值。

### [1] alfworld — `open.obj`
- value: `cabinet 4`  区间 [264,273)
```
... In it, you see a soapbottle 2.⏎go to cabinet 4 -> You arrive at cabinet 4. The 【cabinet 4】 is closed.⏎[THINKING]⏎I've checked cabinets 1, 2, and 3, and none contained a s...
```
### [2] alfworld — `take.from`
- value: `drawer 5`  区间 [2774,2782)
```
...It didn't list the contents.⏎I found "fork 1" in drawer 3.⏎I found "knife 1" in 【drawer 5】.⏎It is highly probable that "knife 1" is the butterknife.⏎I will take it.⏎⏎Plan...
```
### [3] alfworld — `go.to`
- value: `garbagecan 1`  区间 [1043,1055)
```
...ows `move soapbar 1 to toilet 1`. It doesn't explicitly show `move soapbar 1 to 【garbagecan 1】` in the *current* list because I am not at the garbagecan.⏎I should take the se...
```
### [4] alfworld — `go.to`
- value: `fridge 1`  区间 [3625,3633)
```
...k. I will move to the fridge to open it and search for the bread.⏎ACTION: go to 【fridge 1】"⏎Done. ⏎(Self-Correction/Note during generation prep: I should ensure the reaso...
```
### [5] alfworld — `clean.with`
- value: `sinkbasin 1`  区间 [712,723)
```
... to coffeemachine 1.⏎3. Put cup 1 in coffeemachine 1.⏎⏎Action: clean cup 1 with 【sinkbasin 1】....
```
### [6] alfworld — `go.to`
- value: `fridge 1`  区间 [1473,1481)
```
...ridge 1.⏎Action: go to fridge 1.⏎Done. ⏎Let's verify the command format: `go to 【fridge 1】` matches exactly.⏎Proceed. ⏎Self-Correction/Refinement during thought: Sometime...
```
### [7] alfworld — `take.obj`
- value: `cd 3`  区间 [406,410)
```
...ry. Now I need to take cd 3.⏎Wait, the admissible commands do not include "take 【cd 3】 from drawer 4".⏎Let me check the admissible commands again.⏎- close drawer 4⏎- ...
```
### [8] alfworld — `go.to`
- value: `cabinet 1`  区间 [4666,4675)
```
...visible, progressing directly toward acquiring the target object.⏎ACTION: go to 【cabinet 1】⏎Matches perfectly. ⏎Proceeds. ⏎[Output Generation] (Proceeds)⏎*(Done.)*...
```
### [9] alfworld — `go.to`
- value: `drawer 3`  区间 [1003,1011)
```
...losed? I didn't open it in turn 6, I just arrived. Wait, in turn 6 I arrived at 【drawer 3】 and saw nothing. I didn't open it. Maybe it's closed?)⏎- drawer 4 (nothing on i...
```
### [10] alfworld — `move.obj`
- value: `tomato 1`  区间 [895,903)
```
... the tomato.⏎3.  Next step: Put the tomato in the microwave.⏎4.  Command: `move 【tomato 1】 to microwave 1`.⏎⏎...
```
### [11] alfworld — `go.to`
- value: `cabinet 1`  区间 [2056,2065)
```
... *Self-Correction/Verification during generation prep*: ⏎The prompt says "go to 【cabinet 1】" is admissible. ⏎...
```
### [12] alfworld — `go.to`
- value: `desk 2`  区间 [1269,1275)
```
... go to desk 2 to look for the mug.⏎If not there, I'll check drawers.⏎I'll go to 【desk 2】.⏎...
```
### [13] alfworld — `heat.with`
- value: `microwave 1`  区间 [721,732)
```
...nd get the mug 1.⏎Wait, let's look at the admissible commands.⏎"heat cup 1 with 【microwave 1】" is available.⏎"drop cup 1" is NOT in the list.⏎"inventory" is available.⏎"look...
```
### [14] alfworld — `go.to`
- value: `drawer 8`  区间 [482,490)
```
...continue checking the remaining drawers.⏎The next one is drawer 8.⏎I will go to 【drawer 8】 and open it.⏎...
```
### [15] alfworld — `clean.with`
- value: `sinkbasin 1`  区间 [535,546)
```
... clean the soapbar first.⏎The admissible commands include "clean soapbar 2 with 【sinkbasin 1】".⏎I should execute this command to clean the soapbar.⏎...
```
### [16] alfworld — `move.obj`
- value: `remotecontrol 1`  区间 [1098,1113)
```
...`.⏎It shows `move remotecontrol 1 to coffeetable 1`.⏎This implies I am holding `【remotecontrol 1】` and the game thinks I might want to put it down.⏎...
```
### [17] alfworld — `go.to`
- value: `coffeemachine 1`  区间 [6718,6733)
```
...o check if the missing peppershaker is located on or inside it. "⏎ACTION: go to 【coffeemachine 1】⏎Matches perfectly. ⏎Proceeds. ⏎[Output Generation] -> *Self-Correction/Verifica...
```
### [18] alfworld — `take.from`
- value: `countertop 1`  区间 [242,254)
```
...eppershaker 1, a saltshaker 1, a spatula 2, and a spatula 1.⏎[THINKING]⏎I am at 【countertop 1】.⏎I see a mug 1. A mug is a type of cup.⏎The task is to put a cool cup in the mi...
```
### [19] alfworld — `move.to`
- value: `countertop 1`  区间 [2073,2085)
```
...coffeemachine".⏎Is it possible that "coffeemachine 1" is not a receptacle, but "【countertop 1】" is where it sits?⏎Or maybe I need to use the coffeemachine? "use coffeemachine...
```
### [20] alfworld — `go.to`
- value: `cabinet 3`  区间 [1925,1934)
```
...⏎I need knives.⏎I will proceed to cabinet 3 to check for knives.⏎⏎Action: go to 【cabinet 3】.⏎Then open it.⏎⏎...
```
### [21] alfworld — `go.to`
- value: `cabinet 16`  区间 [2188,2198)
```
... in countertop.⏎Current location: cabinet 15.⏎Next: cabinet 16.⏎Command: `go to 【cabinet 16】`⏎Matches admissible list.⏎Ready. ⏎Output Generation. ⏎(Note: I will just output...
```
### [22] alfworld — `go.to`
- value: `garbagecan 1`  区间 [726,738)
```
...ve egg 1 to microwave 1`, but I need to go to the garbagecan first.⏎Let's go to 【garbagecan 1】.⏎Then I will use the appropriate command to put the egg in the garbagecan.⏎...
```
### [23] alfworld — `go.to`
- value: `fridge 1`  区间 [1225,1233)
```
...top, but fridge is the most reliable.⏎I'll go to fridge 1.⏎Done. ⏎Action: go to 【fridge 1】⏎Let's double check. Yes.⏎Proceed. ⏎Output matches requirement.⏎Reasoning: The t...
```
### [24] alfworld — `go.to`
- value: `garbagecan 1`  区间 [4517,4529)
```
...D, cabinets 1, 3, 4 are often just surfaces or open. I checked them.⏎I'll go to 【garbagecan 1】.⏎...
```
### [25] alfworld — `go.to`
- value: `drawer 2`  区间 [297,305)
```
... empty. I need to continue searching for keychains. I'll check the next drawer, 【drawer 2】, as drawers are common places for small items like keychains....
```
### [26] alfworld — `take.from`
- value: `shelf 1`  区间 [207,214)
```
...ndle 1, a spraybottle 2, and a tissuebox 2.⏎[THINKING]⏎I found spraybottle 2 on 【shelf 1】. I need to take it. ...
```
### [27] alfworld — `move.obj`
- value: `keychain 1`  区间 [4176,4186)
```
...ation. I'm at sofa 1. So I can only move keychain 1 to sofa 1.⏎⏎So I will `move 【keychain 1】 to sofa 1`.⏎Then `take keychain 2 from sofa 1`.⏎Then `go to safe 1`.⏎Then `move...
```
### [28] alfworld — `go.to`
- value: `drawer 1`  区间 [2295,2303)
```
...y, in many ALFRED/TextWorld tasks, boxes are in drawers or cabinets. I'll go to 【drawer 1】. If it's empty, I'll check others. ⏎I will write the reasoning and then the act...
```
### [29] alfworld — `go.to`
- value: `diningtable 1`  区间 [673,686)
```
...⏎I will check the dining table first.⏎⏎Current location: drawer 4.⏎Next target: 【diningtable 1】....
```
### [30] alfworld — `clean.obj`
- value: `pan 1`  区间 [629,634)
```
...ing, I will need to go to a countertop and place the pan there.⏎⏎Plan:⏎1. Clean 【pan 1】 with sinkbasin 1.⏎2. Go to a countertop (e.g., countertop 1).⏎3. ...
```
### [31] alfworld — `go.to`
- value: `desk 1`  区间 [706,712)
```
...ed to look elsewhere.⏎Wait, if I go to the desk, I can look around.⏎Let's go to 【desk 1】 first.⏎⏎Admissible commands:⏎...
```
### [32] alfworld — `go.to`
- value: `cabinet 2`  区间 [618,627)
```
...ntertops, fridge, sink.⏎I should check other cabinets or countertops.⏎Let's try 【cabinet 2】.⏎⏎...
```
### [33] alfworld — `go.to`
- value: `stoveburner 1`  区间 [1116,1129)
```
...stoveburner 1` is available.⏎Proceed. ⏎One minor thing: sometimes "put pan 1 in 【stoveburner 1】" is available immediately if I'm at the fridge? ...
```
### [34] alfworld — `go.to`
- value: `countertop 1`  区间 [1853,1865)
```
...e garbagecan already? No, task says put a spraybottle in garbagecan.⏎I'll go to 【countertop 1】.⏎Done. ⏎Output matches. ⏎Proceed. ⏎[Self-Correction/Refinement during thought]⏎...
```
### [35] alfworld — `go.to`
- value: `drawer 19`  区间 [522,531)
```
...ld go to drawer 19 next.⏎Wait, looking at the admissible commands, I can `go to 【drawer 19】`.⏎Let's do that.⏎...
```
### [36] alfworld — `use.obj`
- value: `desklamp 1`  区间 [1204,1214)
```
...l) using the lamp.⏎⏎Wait, is there a specific command like "examine bowl 1 with 【desklamp 1】"?⏎...
```
### [37] alfworld — `go.to`
- value: `sinkbasin 1`  区间 [481,492)
```
...l 1` and trying to find a place to put it down so I can pick up `cloth 1` from `【sinkbasin 1】`. I've tried garbagecan, bathtubbasin, handtowelholder, toilet, and toiletpaper...
```
### [38] alfworld — `go.to`
- value: `desk 1`  区间 [416,422)
```
...or the pencil and the desklamp.⏎Let's start by going to desk 1.⏎⏎Plan:⏎1. Go to 【desk 1】.⏎2. Look/examine to see if there is a pencil and a desklamp.⏎3. If not, check d...
```
### [39] alfworld — `go.to`
- value: `cabinet 1`  区间 [414,423)
```
...on countertops. I should check the cabinets or drawers. Let's start by checking 【cabinet 1】....
```
### [40] alfworld — `open.obj`
- value: `cabinet 3`  区间 [292,301)
```
... You arrive at cabinet 3. The cabinet 3 is closed.⏎[THINKING]⏎I am currently at 【cabinet 3】, which is closed. I have already found cloth 1 in cabinet 1. ...
```
### [41] alfworld — `go.to`
- value: `sinkbasin 1`  区间 [1773,1784)
```
...o to sinkbasin 1`.⏎Actually, I'll try `go to bathtubbasin 1`.⏎Let's just `go to 【sinkbasin 1】`.⏎Wait, the prompt says "put a clean cloth in cabinet". ...
```
### [42] alfworld — `go.to`
- value: `fridge 1`  区间 [775,783)
```
... to fridge 1".⏎I will go to the fridge first.⏎⏎Plan:⏎1. Go to fridge 1.⏎2. Open 【fridge 1】.⏎3. Take tomato.⏎4. If needed, cool it (maybe it's already cool, or I need to p...
```
### [43] alfworld — `open.obj`
- value: `cabinet 1`  区间 [842,851)
```
...ato (likely in the fridge).⏎5. Put the cool tomato on a countertop.⏎⏎Let's open 【cabinet 1】....
```
### [44] alfworld — `go.to`
- value: `dresser 1`  区间 [1603,1612)
```
...stick with it.⏎Output matches requirement.⏎Proceed. ⏎Action line: ACTION: go to 【dresser 1】⏎Done. ⏎Let's generate. ⏎[Output Generation]⏎- Reasoning: I need to find a watch...
```
### [45] alfworld — `open.obj`
- value: `microwave 1`  区间 [830,841)
```
...` command handles the interaction.⏎Let's look at the commands. `heat cup 1 with 【microwave 1】` is available.⏎But the microwave is closed. ...
```
### [46] alfworld — `take.from`
- value: `countertop 2`  区间 [1362,1374)
```
...djective "cool" is specific.⏎Let's check the commands. I can `take apple 1 from 【countertop 2】`.⏎Then I need to go to the fridge, put it in, wait? Or maybe just put it in and...
```
### [47] alfworld — `take.from`
- value: `bed 1`  区间 [503,508)
```
... take pillow 1 from bed 1.⏎Let's verify the command format: "take pillow 1 from 【bed 1】" is in the admissible commands list.⏎Proceed. ⏎Next steps after this: go to des...
```
### [48] alfworld — `move.to`
- value: `diningtable 1`  区间 [1941,1954)
```
...o diningtable 1 first to refresh the state or drop it.⏎Actually, `move cup 1 to 【diningtable 1】` is available. I will use it.⏎Then I'll go to coffeemachine 1.⏎...
```
### [49] alfworld — `go.to`
- value: `sinkbasin 1`  区间 [9743,9754)
```
...wel 1` and it's available at the sink. I'll go there. ⏎All good. ⏎ACTION: go to 【sinkbasin 1】⏎Done. ⏎[Output Generation] (Proceeds)...
```
### [50] alfworld — `go.to`
- value: `drawer 2`  区间 [335,343)
```
... a spatula. I need to check other drawers or cabinets for a spatula. I'll check 【drawer 2】 next....
```

## 抽不到(found=false)案例 — 核对是否确实未出现

### [NG1] alfworld — `go.to`
- value: `microwave 1`
- text 末 120 字符:
```

I have the tomato 2 in my inventory.
The task is to heat the tomato and put it in the fridge.
I need to heat it first.

```
### [NG2] alfworld — `go.to`
- value: `shelf 2`
- text 末 120 字符:
```
e shelf 1, you see a watch 1.
[THINKING]
I have checked all drawers (1-17) and the desk (1) without finding a desklamp.

```
### [NG3] alfworld — `go.to`
- value: `cabinet 8`
- text 末 120 字符:
```
rrive at cabinet 7. On the cabinet 7, you see nothing.
[THINKING]
I have checked cabinets 1 through 7 and found no pot.

```
### [NG4] alfworld — `go.to`
- value: `drawer 4`
- text 末 120 字符:
```
. The drawer 3 is open. In it, you see nothing.
[THINKING]
Drawer 3 is empty. I need to continue searching for a spoon. 
```
### [NG5] alfworld — `go.to`
- value: `drawer 1`
- text 末 120 字符:
```
 put two spraybottle in garbagecan.
[HISTORY]
(start)
[THINKING]
The task is to put two spraybottles in the garbagecan.

```
### [NG6] alfworld — `go.to`
- value: `coffeetable 1`
- text 末 120 字符:
```
amp on it, or hold the desklamp and use it on the tissuebox. Let's look at the commands. "use desklamp 1" is available. 
```
### [NG7] alfworld — `go.to`
- value: `fridge 1`
- text 末 120 字符:
```
 countertops.
I should start by checking the fridge, as it's a common place for bottles.
Let's go to the fridge first.


```
### [NG8] alfworld — `take.obj`
- value: `pencil 1`
- text 末 120 字符:
```
sser 1
- take cd 1 from dresser 1
- take cd 2 from drawer 1
- take cd 3 from dresser 1
- take cellphone 1 from drawer 2

```
### [NG9] alfworld — `go.to`
- value: `sinkbasin 1`
- text 末 120 字符:
```
e checked drawers 1 through 6 and found no soapbar.
I have checked countertop 1 and found a soapbottle, but no soapbar.

```
### [NG10] alfworld — `go.to`
- value: `garbagecan 1`
- text 末 120 字符:
```
ecked:
- cabinet 1 (tissuebox 2)
- cabinet 2 (toiletpaper 2)
- cabinet 3 (spraybottle 2 - taken)
- cabinet 4 (candle 2)

```
