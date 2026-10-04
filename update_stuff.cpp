

#include <cstdlib>
#include <iostream>
#include <string>


bool run(const std::string& cmd) {
    std::cout << "\n> " << cmd << "\n";
    return std::system(cmd.c_str()) == 0;
}


bool exists(const std::string& program) {
#ifdef _WIN32
    return std::system(("where " + program + " >nul 2>&1").c_str()) == 0;
#else
    return std::system(("command -v " + program + " >/dev/null 2>&1").c_str()) == 0;
#endif
}


#ifdef _WIN32

void windows() {
    if (!exists("winget")) {
        std::cout << "winget not found. Install 'App Installer' from the Microsoft Store.\n";
        return;
    }
    const char* common = " -e --accept-source-agreements --accept-package-agreements";

    // yt-dlp
    if (exists("yt-dlp")) run(std::string("winget upgrade --id yt-dlp.yt-dlp") + common);
    else                  run(std::string("winget install --id yt-dlp.yt-dlp") + common);

    // ffmpeg
    if (exists("ffmpeg")) run(std::string("winget upgrade --id Gyan.FFmpeg") + common);
    else                  run(std::string("winget install --id Gyan.FFmpeg") + common);
}


#elif defined(__APPLE__)

void macos() {
    if (!exists("brew")) {
        std::cout << "Homebrew not found. Install it from https://brew.sh and run again.\n";
        return;
    }
    run("brew update");
    for (std::string pkg : {"yt-dlp", "ffmpeg"}) {
        if (exists(pkg)) run("brew upgrade " + pkg);  
        else             run("brew install " + pkg); 
    }
}


#else

void linuxOS() {
  
    const char* home = std::getenv("HOME");
    std::string dir = std::string(home ? home : ".") + "/.local/bin";
    std::string target = dir + "/yt-dlp";
    const std::string url =
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux";

    run("mkdir -p \"" + dir + "\"");
    if (exists("curl"))
        run("curl -L --fail -o \"" + target + "\" " + url);
    else if (exists("wget"))
        run("wget -O \"" + target + "\" " + url);
    else
        std::cout << "Need curl or wget to download yt-dlp.\n";
    run("chmod a+rx \"" + target + "\"");
    std::cout << "(Make sure " << dir << " is in your PATH)\n";


    if      (exists("apt-get")) run("sudo apt-get update && sudo apt-get install -y ffmpeg");
    else if (exists("dnf"))     run("sudo dnf install -y ffmpeg-free");  
    else if (exists("pacman"))  run("sudo pacman -Syu --noconfirm ffmpeg");
    else if (exists("zypper"))  run("sudo zypper install -y ffmpeg");
    else std::cout << "Unknown package manager. Please install ffmpeg manually.\n";
}

#endif

int main() {
#ifdef _WIN32
    std::cout << "Detected: Windows\n";
    windows();
#elif defined(__APPLE__)
    std::cout << "Detected: macOS\n";
    macos();
#else
    std::cout << "Detected: Linux\n";
    linuxOS();
#endif

    std::cout << "\n--- Versions ---\n";
    run("yt-dlp --version");
    run("ffmpeg -version");
    return 0;
}
