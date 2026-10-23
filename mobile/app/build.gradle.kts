plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("app.cash.paparazzi")
}

android {
    namespace = "local.friday.remote"
    compileSdk = 35
    defaultConfig {
        applicationId = "local.friday.remote"
        minSdk = 30 // Android 11: Keystore keys that open with fingerprint OR PIN, per use
        targetSdk = 35 // edge-to-edge is enforced from 35: handled with enableEdgeToEdge + Scaffold insets (§71)
        versionCode = 8
        versionName = "2.3"
        ndk { abiFilters += "arm64-v8a" } // every current phone, incl. the owner's Xiaomi 13T Pro; 4 ABIs = +70 MB
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug") // personal sideload; same key for every update
        }
    }
    buildFeatures { compose = true }
    // §73 FRIDAY's voice model (185 MB) comes from the PC's models/vanira at build time — never committed to git
    sourceSets["main"].assets.srcDirs("../../models/vanira")
    check(file("../../models/vanira/tts.onnx").exists()) { "models/vanira/tts.onnx missing: run FRIDAY once on the PC (it downloads the voice)" }
    androidResources { noCompress += "onnx" }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // ponytail: BOM pinned to what AGP 8.7 / compileSdk 35 / Kotlin 2.0 build; the skill's newest BOM needs an AGP+SDK upgrade
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.fragment:fragment-ktx:1.8.5") // BiometricPrompt needs a FragmentActivity
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0") // §73 runs the voice model on the phone
    testImplementation("org.json:json:20240303") // real org.json for JVM tests (android.jar has stubs)
}
