# Provenance: files copied from the v1 repository

> **Summary:** The 125 files of four folders copied byte-identical (`cp -p`) on 2026-11-02 from `ai-agent-accessibility` at commit `5e4a05a` into the same relative paths here: `docs/feasibility/` (67), `studies/v2-pilot/` (14), `scripts/probe/breakingweb/` (23), `scripts/realworld/` (21). Each row gives the path, its sha256 and whether the file is the same at the v1 freeze tag `v1-final` (`b562fc6`): 91 same, 2 changed after the tag, 32 added after the tag. The v1 repository keeps its copies; nothing there was deleted.

## How the copy was made and checked

- Source: `/home/alexjia/.workspace/ai-agent-accessibility`, branch `master`, commit `5e4a05a99a532b3c1f1ea08c36f9ff08306e8068`, clean tree for these four folders (`git status --short` empty).
- File set: `git ls-files` of the four folders (tracked files only). The ignored `scripts/probe/breakingweb/__pycache__/` was not copied.
- Copy: `cp -p` per file, so the modification times are those of the source checkout.
- Check: for every file, sha256 of `git show 5e4a05a:<path>` equals sha256 of the copy here. 125 of 125 matched (2026-11-02, about 05:40 UTC).
- Re-check at any time, from this repository's root: `sha256sum -c provenance/SHA256SUMS.copied` (same list as the table, in `sha256sum` format).
- v1-final column: `same` means the blob at `v1-final:<path>` equals the blob at `5e4a05a`; `changed` means the file was edited in `a9e6346` or `5e4a05a`; `new` means the file did not exist at `v1-final`.

Files changed after `v1-final`: `scripts/probe/breakingweb/README.md`, `studies/v2-pilot/DESIGN.md`. They were committed in `a9e6346` (v2 readiness work) and are v2 material; the v1 study does not read them.

## Files

| Path | sha256 | v1-final |
|---|---|---|
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__alt.report.json` | `b33fb4c2be54303ad6814238d7688c26fd945bd9ac4a340261e07a12438bde42` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__headings.report.json` | `7e3a21e378bf6e11593849ca509a75ae3e0549fbfd35a27a798e490bfe3f095b` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__labels.report.json` | `fe1065d9b27e413af59693fe092521b75553e2a53571280bb07be3b8689cc79e` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__landmarks.report.json` | `16a15de9777bcf7ad1a1b4d50dca7b314c97a04f2e977bdde987000cedadbe55` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__names.report.json` | `46456f3f6b0f4a1272777fd476682bf5101f65e0670e2e37765e744e995dc93a` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__none.report.json` | `de802fe1548ed5dbbd5323040f6ed45e16ae6de5ba6ccb3948c1f97cb7d1c962` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/amazon__tableheads.report.json` | `6bfcdc7e4bd56bd85ded44ad4d7649825bf184e75e1498ee9ec136da812c53b4` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__alt.report.json` | `235d2ac99d0d9e7f6a87de805d0430f81e35057501be02cd938ec015b3504d88` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__headings.report.json` | `e165bd6d38d2c557592db9fc457bd1bd5dae1941d363affdfeabc51ad511597b` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__labels.report.json` | `0bccb0e27c6c1617ef0173da60cd64dca79e1da6eab436604b3931458ea46cf5` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__landmarks.report.json` | `8df8ec8516a65f02ebc7e198492c02092c746fafbf156a7354c67b1acb6f3bf1` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__names.report.json` | `5f2c4993f179ba15f7256efb1e587c8c616daf39dd9e7bafa07cbbb6101eb4cc` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__none.report.json` | `cb13c0253c5483993e7b932b6cf7e4ebecfb1c28b1dbeb850eb6f6246b589c27` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/booking__tableheads.report.json` | `0b8312dc063be033a1335450a0a1708b89ef821ddc115873c4b883cbe8717a7c` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__alt.report.json` | `d133c16319b41534137549bf892866f47bdf83a4545a5dcfa5954565a1881bf6` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__headings.report.json` | `154578c7d158600798adc249bfae2fb9736d1a14d76a68cc1876b7edcdf8c88b` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__labels.report.json` | `07cbeac7225596b0a2e12e06cd82e8f3e1a4fd7c23057feb0d82eeb7394cb1db` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__landmarks.report.json` | `dd9cfe8eee72e53779acee0eafbf8198110e96f8a4116251016950b6acf96085` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__names.report.json` | `797891f6a9ec69f035775fad894bd0ce445bec0d7ef5b0ebb43b1fb495e68fae` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__none.report.json` | `45264a46f06594459244494981105746e24ba9baaa77b71de12fca24d60ebd46` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/gmail__tableheads.report.json` | `28ebb57d68ff627b6b579c7dbb57a8b4e380b5f506879ba7dce952d44f4240d7` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__alt.report.json` | `2395f036101888abdf6c28416c7d240873ff217478ede7125830cf7e5e4d1f22` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__headings.report.json` | `6f0e87449ec2a6b363c3bbc0b08baaef3e9cba4cced359491ec89a57ac5b31bd` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__labels.report.json` | `99c014d611bfd72af58b67228b1697f4ff74dd85e820a0c420657205ff6f816c` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__landmarks.report.json` | `bbdae1fd9465d42ea7f551e892fa98b3f8aa7718ecc8dce545d9982dfe0d1c40` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__names.report.json` | `ac91f657e0484d0aa8b5e3bdf4a0870cde2fd1b13f8d03b5e6b68b3776a44ab7` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__none.report.json` | `8989761d9df6eeb5ea3724686dbbb237adc5fe533e2e2f83023dcf31728d42c0` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/lms__tableheads.report.json` | `298ec2178cc9788d5c2c2403700cb7ddf80fcbeffd9beb349f970ae95285e023` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__alt.report.json` | `05bb2d11413861bcfa48ca3ba066acd9f3bdbd0de6643a229456137df785a523` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__headings.report.json` | `a373ffbaad8a7e9cdf63bdf142fb8de150434a29e90ea8f73debd20cea68d561` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__labels.report.json` | `eadefc76ed2484ceb8e04bd9defe8dd465e125fb1a057ff4695f4d01d32dce0c` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__landmarks.report.json` | `cfc2bd729f90461f008da8590ee38b9b85a4fcbc7dd6fa9e50c23178007d0aa6` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__names.report.json` | `d0a40f9b244eb39293e6a2b61324c977093eb7a1bf86e6f9cb4c93de426d0f4f` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__none.report.json` | `751bb25e4e1a622b55e08fb2f48b26f5844be7d6dbee0ef86af634ead3c22df8` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/patient_portal__tableheads.report.json` | `7cdcff4cde2d9701f9b14db9bdc55045bae23bff5fedd0b1febfeb7b7f97ab38` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__alt.report.json` | `660e1089b1b2fadbf65a45ed3eb7bfdc7819f66be980ed062718bbd822cb9497` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__headings.report.json` | `cf92a29f9b6aafed76af1711860396201dc2812b61695effef4b676a74856fad` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__labels.report.json` | `9aa295f4b45f42bae11f01ecfac25bb119a63fe0ad49e35b73d8d5eee9815407` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__landmarks.report.json` | `49d4dca30cd11b16dad86d4ea2736f9a757660a7c8bf038c28dcc82063d160c6` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__names.report.json` | `2391844d882da6c5b4f7d48c91c2e88eb2f15b756bbce1ee43887d341f8c396c` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__none.report.json` | `9373a780c580e4d40bc44f325609c8f0a07c5e29009b4b71761bef4db227423c` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/reddit__tableheads.report.json` | `0cd2752174c7e5b54f70d6eaf627a07a9ff9188a397e1260ec95a22dd8943ba7` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__alt.report.json` | `d7c73294e0b5b98b74b224c20506308406b031e00f94268328e78e834d96c9eb` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__headings.report.json` | `fc96e1ff43de0ce9a8f78d9840eca7b6f54980faa4581f3fc03ef93cc0e13844` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__labels.report.json` | `c80fb64ffa1f9fd3ee2fe331dbe50038acc27404a2010cde2698f85823cfcdb3` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__landmarks.report.json` | `6e4fd10fd5a08e42f07033c82dd4beaf736f263ac5941d464dad339ad5c9dc70` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__names.report.json` | `90b8a0e117e0c33780df6edf92ed6b819966c79675c2c72be1c258bc15adcf46` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__none.report.json` | `8a2fd11569a748636282f1e45e9933ec79afe148d533df3a7b207060a96ab943` | same |
| `docs/feasibility/2026-10-29-breakingweb-batch/robinhood__tableheads.report.json` | `61d84b7b4a9ed0bc8fd101df38152f20b0f203606d53b55d46fcb88ce6c78db5` | same |
| `docs/feasibility/2026-10-29-breakingweb.md` | `26de7a12872dae51a53745d8a454a3d3478a9e0d7c477a4638f890a67633f840` | same |
| `docs/feasibility/2026-10-30-browseruse-footprint.json` | `514e5081465cba0fa400ee7a9318a0d4d74f2f90593af6d780187f74757f7bc8` | same |
| `docs/feasibility/2026-10-30-browseruse-footprint.md` | `488c0d8e0fe10ce3e7eb38bebc4d19f29376665e07ab3207400705b083b4a566` | same |
| `docs/feasibility/2026-10-30-function-equivalence.json` | `59ba5b7e507a902b08d32093f56afa428c8c13dd7f6712322e05bb12e0834e7e` | same |
| `docs/feasibility/2026-10-30-function-equivalence.md` | `2e44d8fee43743156a0a831671142ef4c219e168dff869d00651aaef550ec388` | same |
| `docs/feasibility/2026-10-30-on-path-dose.json` | `1f6424a57ab9913685b17c568bb1d1ba65eb842dcdf5b3acecdd66619962284d` | same |
| `docs/feasibility/2026-10-30-on-path-dose.md` | `3c379ea808896dc38233ae7ea8f590aa71a87a405afe0f39c6f6f041026d3890` | same |
| `docs/feasibility/2026-10-30-pipeline-smoke.json` | `ac4b300189b9c6d670f910d2dc00a5c5c354dad7675b85407e5c85f5d1ca14fd` | same |
| `docs/feasibility/2026-10-30-pipeline-smoke.md` | `cc8d5dac414590d5602e025f884ca0e80797f420eb9b9bbd6f45f461a56bd4ed` | same |
| `docs/feasibility/2026-10-30-replay-feasibility.json` | `725cea240139f18394650fb77c3ab5f18dff992c05a00dc405e9fbb90ac41727` | same |
| `docs/feasibility/2026-10-30-replay-feasibility.md` | `8e53e0a6f326ce9b2d6ebe292b8891164e6c6054a91fccc0673f39e797092626` | same |
| `docs/feasibility/2026-10-30-variant-gate-ua-delta.json` | `7756a7ccd66f7dbc22edb4a23c64885945706d90d8ee8cba8ba4292820369161` | same |
| `docs/feasibility/2026-10-30-variant-gate.json` | `bda54723b6da23d0e9bcb136a0a101795749903b17bc6a14bbad82b55ff6680c` | same |
| `docs/feasibility/2026-10-30-variant-gate.md` | `006c02515e53033de29d9c99e0eb47e56dd2935fa91be65461f45c5532ee918d` | same |
| `docs/feasibility/2026-11-02-h1-wrapper.md` | `8b3d2e8a91dc86081f1b8fdf5a53b328056f12dbec1a39e3220057fd6b1dc903` | new |
| `docs/feasibility/2026-11-02-realworld-kit.json` | `1232017752e4d39579480a31eeef869231b9b5780e896e2a50a4afb02535ef36` | new |
| `docs/feasibility/2026-11-02-realworld-kit.md` | `cf6db91da366a0d3e061f45dfcf3e0678848cee7990cfbc2e16e70a68dca81d3` | new |
| `docs/feasibility/2026-11-02-wrapper-smoke.md` | `ed93618c2e01617fe5d34f859d28b57ff982f373abd7b1c3898662d000c32cdd` | new |
| `scripts/probe/breakingweb/README.md` | `76deb0ae581c049f8309ded5a364ba02960038ff9aa8d17f9266ec2a12206107` | changed |
| `scripts/probe/breakingweb/ablate.py` | `492b0972f91019654fd01f95994ef0d8eea438114ab4cdc21718aadb9d6e6418` | same |
| `scripts/probe/breakingweb/batch.sh` | `01a3029479080f90d41c9b316f62ae86d3025fe7de13611545cabf2d9db02802` | same |
| `scripts/probe/breakingweb/browseruse_capture.py` | `5486a31c4b2aa18bc625594d1edb4d7b77ce59c9f9fbaca76d16e3fed19d3d94` | same |
| `scripts/probe/breakingweb/click_effect.py` | `5bda0f1897c82394b454080c35c2a7ee8a661b6d47de6bf0fdc59fc1adc82124` | same |
| `scripts/probe/breakingweb/click_treated.py` | `71f9ef0512d0489c982d83df96ec061d19c4f55dc92233e4cc3d1bdea3f3a161` | same |
| `scripts/probe/breakingweb/codemod.py` | `02b3190ff81d153f8ceade194f6076f0adb093273298a7772ca2e7347c7f8045` | same |
| `scripts/probe/breakingweb/h1_budget.py` | `2269579c82785d9b550ff3922e8cc414524d611e33bd065857107760a48f8759` | new |
| `scripts/probe/breakingweb/h1_selftest.py` | `dbfe519026b8f4783bd68123cbe95e7eb1e4b59c54922354ee24399a70ab8982` | new |
| `scripts/probe/breakingweb/h1_wrapper.py` | `f1342dbe1035d70677491dee667ee735da04b9a9f8dd7092ab5f65a8de793b27` | new |
| `scripts/probe/breakingweb/inventory.py` | `31bfbeb37704b8b486d8308bddb60a89ef6976ac6b2b169987905f8406beb970` | same |
| `scripts/probe/breakingweb/on_path_dose.py` | `3ed4779858a76da0f5bc8477767d1385332bf8faacc2206cd190fbc7420a3f5f` | same |
| `scripts/probe/breakingweb/path_replay.py` | `a8af467288f0ba0b8555b722627fa67b6ed2e731affcd8eb7fe84f5cb1a65038` | same |
| `scripts/probe/breakingweb/pilot_plan.py` | `1d88887b478588a71293e76edcbfe9312df48e956411bcba4cc0bbda77ecb497` | same |
| `scripts/probe/breakingweb/pilot_precision.py` | `415d29e90a0fa062648f2d814625685193cb4dc92e89e16025fbf29c8789bdda` | same |
| `scripts/probe/breakingweb/pipeline_smoke.py` | `f2bef1b67cfebecab7cf331fa19757891bdc8b9d5f9d7c1eea6a6d7458a737a9` | same |
| `scripts/probe/breakingweb/replay.py` | `b4e179a4afa8fdbe041c0ace74d0359628e693306c5950e948e404901d439508` | same |
| `scripts/probe/breakingweb/replay_report.py` | `4e67d6d07148d15559f51e44b2f5c3194b664c44e27ac2f496685644b80bfd2e` | same |
| `scripts/probe/breakingweb/show.py` | `0ca2a80661c19927ab727ce28bbd68ca6520ff31ab3401979285acb4f5ebb057` | same |
| `scripts/probe/breakingweb/ua_delta.py` | `7873d31aef4b56385f54f4ee19eced10957b2b884405b42ac064f1ed71bf5d62` | same |
| `scripts/probe/breakingweb/variant_check.py` | `b1e5bc647bc37a3f723b7a938c32d2b557deacce90598ffc405b0ecdd021ef0f` | same |
| `scripts/probe/breakingweb/variant_gate.py` | `627fb3c46583517a7ededbe0572c0b3fd6bb2bd8f4e73057e4295dd381c51352` | same |
| `scripts/probe/breakingweb/variant_run.py` | `ce56eda4a0e3eb042f7068475774a5f0a3465a063510994e1ca7e9e1eceb623a` | same |
| `scripts/realworld/CAPTURE.md` | `97ffcb271ee2a3ad9066ff636daf18ce50604389b1f2dee0a20c62f489925941` | new |
| `scripts/realworld/TARGETS.md` | `04a9c58211aeaa54807ae437d941028db56b3ab6dc3bc64b7c54d996dd497216` | new |
| `scripts/realworld/analyze.py` | `56945f42ab09a2cf911d4ad33f825343de3c307f08ef0e051c5d24d43abca24b` | new |
| `scripts/realworld/bw_kit_test.py` | `af0a6dad8bcbc57a74b7113e1585548b6ed66d566b78fb8ff28daed937c88dba` | new |
| `scripts/realworld/capture_snippet.js` | `fb9ab38900b0e6a76b6d63761fbf6f467d933117d3afa4f8a73ffac07a17bae7` | new |
| `scripts/realworld/fixtures/alt_neg.html` | `f9dcc83b651ac89ac36355ecaf194ceda2d89e19534cb7bdaacdb89c0bbb0b30` | new |
| `scripts/realworld/fixtures/alt_pos.html` | `242ba167cc6f310347725fd3a34a28305907b6b15787416a550d917a5fb91c74` | new |
| `scripts/realworld/fixtures/headings_neg.html` | `a7c623802f8f070252926d8a2b2d2c2f8fcdb8a2c457b16b29f4817d5bfafa97` | new |
| `scripts/realworld/fixtures/headings_pos.html` | `0b8aea8642f802a379a2a5f43372ad685889b95ee95c259a2df0995aaeb52c44` | new |
| `scripts/realworld/fixtures/labels_neg.html` | `5352ced3ede7fbec3343b6a202228dd1ddbc173c5f15da6894f51de96bd6d7f3` | new |
| `scripts/realworld/fixtures/labels_pos.html` | `72df50704c1f94b33720454442a6afcf47d7fd85cb6e08672c83dc677e7825a8` | new |
| `scripts/realworld/fixtures/landmarks_neg.html` | `8cb3285cb79ddb0ba77fd3b7dafb4711bcd35bae574711ea5de833fd78217b98` | new |
| `scripts/realworld/fixtures/landmarks_pos.html` | `d14f66e9a50c8123051cbf2763a234c2ab00bef5bea68ba51cf334d91d3b07a2` | new |
| `scripts/realworld/fixtures/names_neg.html` | `27c4ba45c8581670fea8a803766e04aba4e3d9703c2c04fff86e0ffd2b72d193` | new |
| `scripts/realworld/fixtures/names_pos.html` | `a62ebf86300a9d3ca703707a2cadfeb6eff5ea052da4883adc305cfaa44aa644` | new |
| `scripts/realworld/fixtures/privacy.html` | `56e35cbd9b7769b25448d87dc2baecf32c504cd23236207fe6b4147242f2be9f` | new |
| `scripts/realworld/fixtures/site.css` | `fecd94e1646c747a1a089ff9711f155def1c9a239e892d90284841f59e7d8d34` | new |
| `scripts/realworld/fixtures/tableheads_neg.html` | `12d1cad837168d5483f5c6031e01cf8af1b18c50f9c63e86d2c39393b7b9df9d` | new |
| `scripts/realworld/fixtures/tableheads_pos.html` | `e6e9e3653cceb8880d9be558d0b530e26d6f289ca140bd6f496c2140ea705b75` | new |
| `scripts/realworld/harness.py` | `8648206d0dacfc35dffb4bf770c7f8fe0a759c03effaaf4c5af89449cc701782` | new |
| `scripts/realworld/selftest.py` | `11536cf21e14cbdf7484ab09e9d5f76585e63a59f147f8d9d93da72d55458be6` | new |
| `studies/v2-pilot/ANALYSIS.md` | `18133fb6a9ef8a4bcc7ebbb4d86cfaf2d65bdef584e59fda7d31aedb95f85fd9` | same |
| `studies/v2-pilot/DEFECTS.md` | `df86260e40dd06cb19cc17efb5eedade1835dc428b7f6d7e931b58a26dbd6c31` | new |
| `studies/v2-pilot/DESIGN.md` | `be145d771bf7d42aac2b04ab4122b490837a03fb2d874fe1e8fd3f9f12c2d011` | changed |
| `studies/v2-pilot/PREDICTIONS.md` | `5c39cc00483f5c412df750a070bc5051bd0471e091f8dbbc7840a7f99ec3e867` | same |
| `studies/v2-pilot/READINESS.md` | `8cdb19367c618da61535351716af4010eb514ff774f2acda39d273bdecb064dd` | new |
| `studies/v2-pilot/TRACE-CODING.md` | `f92d441edbd900c254bd40b610d0402ef0d337f1d11b6ebbc1bdd8213918149a` | new |
| `studies/v2-pilot/cells_by_task.json` | `776d65f47c8134f1c7b1b4f76a57330809fb837b15b63c53719b8c250f95bcde` | same |
| `studies/v2-pilot/cost.json` | `73dc4499972bfb1a59d81156e0789b56bfa85b3c0bfd4adbe120a85e234758b4` | same |
| `studies/v2-pilot/design.yaml` | `5da6fe5863d3ddee43b2d67aa45a0f621f6ef0d7eaf3a784ecb6e51fcfffb814` | same |
| `studies/v2-pilot/mde_sealed.json` | `a576b120e6ed47735e3bcaec0c751d1ab019de551e68c935fb89b3a0a9a35938` | same |
| `studies/v2-pilot/power.json` | `ca7308e1e56342393674e3481c92c1f591a50632bd780b1f045a2191cda7c283` | same |
| `studies/v2-pilot/precision.json` | `fec0cf672864e761a9d58ed77791a7aac971749c2b56e409f77cc43979e7dccc` | same |
| `studies/v2-pilot/select.json` | `299744318335ddc0fa03bd596ba092aa0aa1b7e1eea478358904b7dd1c13f10b` | same |
| `studies/v2-pilot/trace_observer_prompt.md` | `f4b16167b3e8f901d7cb41c09e29109335ae4a0404a7b9ff5ca75bf5921806a6` | new |
