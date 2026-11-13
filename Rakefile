namespace :book do

  # Az összeállításhoz szükséges változók
  version_string = `git describe --tags --abbrev=0 2>/dev/null`.chomp
  if version_string.empty?
    version_string = '2.1.449'
  else
    versions = version_string.split('.')
    version_string = versions[0] + '.' + versions[1] + '.' + versions[2].to_i.next.to_s
  end
  date_string = Time.now.strftime('%Y-%m-%d')
  params = "--attribute revnumber='#{version_string}' --attribute revdate='#{date_string}'"
  header_hash = `git rev-parse --short HEAD`.strip

  # Közreműködők listájának ellenőrzése
  # Összehasonlítja a lista fejlécében tárolt commit hash-t a jelenlegi HEAD-del
  def check_contrib
    if File.exist?('book/contributors.txt')
      current_head_hash = `git rev-parse --short HEAD`.strip
      header = `head -n 1 book/contributors.txt`.strip
      # Regex egyezés keresése, majd a kapott tömb összefűzése szöveggé
      header_hash = header.scan(/[a-f0-9]{7,}/).join

      if header_hash == current_head_hash
        puts "A közreműködők listájának fejlécében lévő hash (#{header_hash}) megegyezik a jelenlegi HEAD-del (#{current_head_hash})"
      else
        puts "A közreműködők listájának fejlécében lévő hash (#{header_hash}) nem egyezik a jelenlegi HEAD-del (#{current_head_hash}), frissítés..."
        sh "rm book/contributors.txt"
        # Feladat újraengedélyezése és újbóli meghívása
        Rake::Task['book/contributors.txt'].reenable
        Rake::Task['book/contributors.txt'].invoke
      end
    end
  end

  desc 'Alapvető könyvformátumok összeállítása'
  task :build => [:build_html, :build_epub, :build_fb2, :build_mobi, :build_pdf] do
    begin
        # Ellenőrzés futtatása
        Rake::Task['book:check'].invoke

        # Kivételkezelés az ellenőrzési hibák figyelmen kívül hagyására
        rescue => e
        puts e.message
        puts 'Hiba a könyvek ellenőrzésekor (figyelmen kívül hagyva)'
    end
  end

  desc 'Alapvető könyvformátumok összeállítása (CI-hez)'
  task :ci => [:build_html, :build_epub, :build_fb2, :build_mobi, :build_pdf] do
      # Ellenőrzés futtatása a hibák figyelmen kívül hagyása nélkül
      Rake::Task['book:check'].invoke
  end

  desc 'Közreműködők listájának előállítása'
  file 'book/contributors.txt' do
      puts 'Közreműködők listájának generálása...'
      sh "echo 'Közreműködők ezen állapot szerint: #{header_hash}\n' > book/contributors.txt"
      sh "git shortlog -s HEAD | grep -v -E '(Straub|Chacon|dependabot)' | cut -f 2- | sort | column -c 120 >> book/contributors.txt"
  end

  desc 'HTML formátum összeállítása'
  task :build_html => 'book/contributors.txt' do
      check_contrib()

      puts 'Átalakítás HTML formátumba...'
      sh "bundle exec asciidoctor #{params} -a data-uri progit.asc"
      puts ' -- HTML kimenet helye: progit.html'

  end

  desc 'EPUB formátum összeállítása'
  task :build_epub => 'book/contributors.txt' do
      check_contrib()

      puts 'Átalakítás EPUB formátumba...'
      sh "bundle exec asciidoctor-epub3 #{params} progit.asc"
      puts ' -- EPUB kimenet helye: progit.epub'

  end

  desc 'FB2 formátum összeállítása'
  task :build_fb2 => 'book/contributors.txt' do
      check_contrib()

      puts 'Átalakítás FB2 formátumba...'
      sh "bundle exec asciidoctor-fb2 #{params} progit.asc"
      puts ' -- FB2 kimenet helye: progit.fb2.zip'

  end

  desc 'Mobi formátum összeállítása'
  task :build_mobi => 'book/contributors.txt' do
      check_contrib()

      puts "Átalakítás Mobi (kf8) formátumba..."
      sh "bundle exec asciidoctor-epub3 #{params} -a ebook-format=kf8 progit.asc"
      puts " -- Mobi kimenet helye: progit.mobi"
  end

  desc 'PDF formátum összeállítása'
  task :build_pdf => 'book/contributors.txt' do
      check_contrib()

      puts 'Átalakítás PDF formátumba... (ez eltarthat egy ideig)'
      sh "bundle exec asciidoctor-pdf #{params} progit.asc 2>/dev/null"
      puts ' -- PDF kimenet helye: progit.pdf'
  end

  desc 'Generált könyvváltozatok ellenőrzése'
  task :check => [:build_html, :build_epub] do
      puts 'Generált könyvek ellenőrzése...'

      sh "htmlproofer progit.html"
      sh "epubcheck progit.epub"
  end

  desc 'Az összes generált fájl törlése'
  task :clean do
    begin
        puts 'Generált fájlok törlése...'

        FileList['book/contributors.txt', 'progit.html', 'progit-kf8.epub', 'progit.epub', 'progit.fb2.zip', 'progit.mobi', 'progit.pdf'].each do |file|
            rm file

            # Kivételkezelés, ha a fájl nem található
            rescue Errno::ENOENT => e
              begin
                  puts e.message
                  puts 'Hiba a fájlok törlésekor (figyelmen kívül hagyva)'
              end
        end
    end
  end

end

task :default => "book:build"
