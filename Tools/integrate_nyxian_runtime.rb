#!/usr/bin/env ruby
# Generates build-only targets from the pinned Nyxian source tree.
require 'xcodeproj'
require 'pathname'

root = File.expand_path('..', __dir__)
generated = File.join(root, 'build', 'NyxianGenerated')
abort 'Run prepare_nyxian_runtime.py first' unless File.file?(File.join(generated, 'SOURCE_SHA256'))

project = Xcodeproj::Project.open(File.join(root, 'LiveContainer.xcodeproj'))
app = project.targets.find { |target| target.name == 'LiveContainer' } or abort 'LiveContainer target missing'
swiftui = project.targets.find { |target| target.name == 'LiveContainerSwiftUI' } or abort 'LiveContainerSwiftUI target missing'

project.targets.select { |target| ['NyxianRuntime', 'NyxianProcess'].include?(target.name) }.each(&:remove_from_project)
project.main_group.children.select { |group| ['NyxianGenerated', 'NyxianCompatibilityGenerated'].include?(group.display_name) }.each(&:remove_from_project)

generated_group = project.main_group.new_group('NyxianGenerated', generated)
compat_group = project.main_group.new_group('NyxianCompatibilityGenerated', File.join(root, 'NyxianCompatibility'))

source_extensions = %w[.c .cc .cpp .m .mm .swift]
files_under = lambda do |base|
  Dir.glob(File.join(base, '**', '*')).select { |path| File.file?(path) && source_extensions.include?(File.extname(path)) }
end

guest_relative = [
  'LindChain/IDEConsole/Utils.c',
  'LindChain/Private/mach/fileport.m',
  'LindChain/ProcEnvironment/litehook/litehook.c',
  'LindChain/ProcEnvironment/LiveContainer/LCBootstrap.m',
  'LindChain/ProcEnvironment/LiveContainer/LCMachOUtils.m',
  'LindChain/ProcEnvironment/LiveContainer/Tweaks/Dead10ccFix.m',
  'LindChain/ProcEnvironment/LiveContainer/Tweaks/Dyld.m',
  'LindChain/ProcEnvironment/LiveContainer/Tweaks/DyldHook.m',
  'LindChain/ProcEnvironment/LiveContainer/Tweaks/NSFileManager+GuestHooks.m',
  'LindChain/ProcEnvironment/LiveContainer/Tweaks/NSUserDefaults.m',
  'LindChain/ProcEnvironment/LiveContainer/Tweaks/UIKit+GuestHooksInit.m',
  'LindChain/ProcEnvironment/LiveContainer/utils.m',
  'LindChain/ProcEnvironment/LiveContainer/ZSign/Utils.mm',
  'LindChain/ProcEnvironment/PEArchiveHandle.m',
  'LindChain/ProcEnvironment/PEFileHandle.m',
  'LindChain/ProcEnvironment/PEFileTable.m',
  'LindChain/ProcEnvironment/PEMachPort.m',
  'LindChain/ProcEnvironment/Shims/application.m',
  'LindChain/ProcEnvironment/Shims/attrstrnilfix.m',
  'LindChain/ProcEnvironment/Shims/environment.m',
  'LindChain/ProcEnvironment/Shims/LSApplicationWorkspace.m',
  'LindChain/ProcEnvironment/Shims/posix_spawn.m',
  'LindChain/ProcEnvironment/Shims/proxy.m',
  'LindChain/ProcEnvironment/Shims/vfork.c',
  'LindChain/ProcEnvironment/Surface/extra/relax.c',
  'LindChain/ProcEnvironment/Surface/trust/signing.c',
  'LindChain/ProcEnvironment/Utils/fd.c',
  'LindChain/ProcEnvironment/Utils/ktfp.c',
  'LindChain/ProcEnvironment/Utils/PEMachOUtils.m',
  'LindChain/ProcEnvironment/Utils/vnode.c',
  'LindChain/Utils/CFTools.c',
  'LindChain/Utils/Swizzle.c',
  'LindChain/Utils/Zip.m'
]
guest_paths = guest_relative.map { |path| File.join(generated, 'Nyxian', path) }
guest_paths.concat(files_under.call(File.join(generated, 'LiveProcess')).reject { |path| path.include?('/Media.xcassets/') })

host_paths = []
host_paths.concat(files_under.call(File.join(generated, 'Nyxian', 'LindChain', 'ProcEnvironment')))
host_paths.concat(files_under.call(File.join(generated, 'Nyxian', 'LindChain', 'WindowServer')))
host_paths.concat(files_under.call(File.join(generated, 'Nyxian', 'LindChain', 'Private')))
host_paths.concat(files_under.call(File.join(generated, 'Nyxian', 'LindChain', 'Utils')))
host_paths.concat(files_under.call(File.join(generated, 'Nyxian', 'LindChain', 'Downloader')))
host_paths << File.join(generated, 'Nyxian', 'LindChain', 'IDEFoundation', 'NXBootstrap.m')
host_paths.concat(files_under.call(File.join(generated, 'Frameworks', 'LiveShim')))
host_paths.concat(files_under.call(File.join(generated, 'Frameworks', 'HWHook')))
host_paths.concat(Dir.glob(File.join(generated, 'Frameworks', 'MobileDevelopmentKit', 'Support', 'MDKThreadPool*.m')))
host_paths.concat([
  File.join(generated, 'LiveProcess', 'LindChain', 'Services', 'applicationmgmtd', 'LDEApplicationObject.m'),
  File.join(generated, 'LiveProcess', 'LindChain', 'Services', 'applicationmgmtd', 'LDEApplicationWorkspace.m'),
  File.join(root, 'NyxianCompatibility', 'FDNyxianUIAdapters.m')
])
host_paths -= guest_paths
host_paths.uniq!
guest_paths.select! { |path| File.file?(path) }
host_paths.select! { |path| File.file?(path) }

add_sources = lambda do |target, paths, group|
  paths.each do |path|
    relative = Pathname.new(path).relative_path_from(Pathname.new(group.real_path)).to_s rescue File.basename(path)
    ref = group.find_file_by_path(relative) || group.new_file(path)
    target.source_build_phase.add_file_reference(ref, true)
  end
end

runtime = project.new_target(:framework, 'NyxianRuntime', :ios, '16.0')
process = project.new_target(:app_extension, 'NyxianProcess', :ios, '16.0')
add_sources.call(runtime, host_paths.reject { |path| path.start_with?(File.join(root, 'NyxianCompatibility')) }, generated_group)
add_sources.call(runtime, host_paths.select { |path| path.start_with?(File.join(root, 'NyxianCompatibility')) }, compat_group)
add_sources.call(process, guest_paths, generated_group)

common_headers = [
  File.join(generated, 'Nyxian'), File.join(generated, 'LiveProcess'),
  File.join(generated, 'Frameworks'), File.join(generated, 'Frameworks', 'LiveShim'),
  File.join(root, 'NyxianCompatibility'), generated
]

[runtime, process].each do |target|
  target.build_configurations.each do |config|
    settings = config.build_settings
    settings['IPHONEOS_DEPLOYMENT_TARGET'] = '16.0'
    settings['HEADER_SEARCH_PATHS'] = ['$(inherited)'] + common_headers
    settings['GCC_PREPROCESSOR_DEFINITIONS'] = ['$(inherited)', 'LCUtils=NXLCUtils', 'ZSigner=NXZSigner']
    settings['CLANG_ENABLE_MODULES'] = 'YES'
    settings['CLANG_CXX_LANGUAGE_STANDARD'] = 'gnu++20'
    settings['ENABLE_BITCODE'] = 'NO'
    settings['CODE_SIGNING_ALLOWED'] = 'NO'
  end
end

runtime.build_configurations.each do |config|
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.fs.flekdeck.NyxianRuntime'
  config.build_settings['DEFINES_MODULE'] = 'YES'
  config.build_settings['SKIP_INSTALL'] = 'YES'
end

process.build_configurations.each do |config|
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.fs.flekdeck.NyxianProcess'
  config.build_settings['INFOPLIST_FILE'] = File.join(root, 'NyxianCompatibility', 'NyxianProcess-Info.plist')
  config.build_settings['CODE_SIGN_ENTITLEMENTS'] = File.join(root, 'NyxianCompatibility', 'NyxianProcess.entitlements')
  config.build_settings['SKIP_INSTALL'] = 'YES'
end

process.add_dependency(runtime)
process.frameworks_build_phase.add_file_reference(runtime.product_reference, true)
swiftui.add_dependency(runtime)
swiftui.frameworks_build_phase.add_file_reference(runtime.product_reference, true)
app.add_dependency(runtime)
app.add_dependency(process)

embed_frameworks = app.copy_files_build_phases.find { |phase| phase.name == 'Embed Frameworks' } || app.new_copy_files_build_phase('Embed Frameworks')
embed_frameworks.symbol_dst_subfolder_spec = :frameworks
runtime_build_file = embed_frameworks.add_file_reference(runtime.product_reference, true)
runtime_build_file.settings = { 'ATTRIBUTES' => ['CodeSignOnCopy', 'RemoveHeadersOnCopy'] }

embed_extensions = app.copy_files_build_phases.find { |phase| phase.name.include?('Embed') && phase.dst_subfolder_spec == '13' } || app.new_copy_files_build_phase('Embed Nyxian Extension')
embed_extensions.dst_subfolder_spec = '13'
process_build_file = embed_extensions.add_file_reference(process.product_reference, true)
process_build_file.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }

shared_ref = generated_group.new_file(File.join(generated, 'Shared'))
kext_ref = generated_group.new_file(File.join(generated, 'KEXTs'))
app.resources_build_phase.add_file_reference(shared_ref, true)
app.resources_build_phase.add_file_reference(kext_ref, true)

project.save
puts "Integrated #{host_paths.length} host sources and #{guest_paths.length} process sources"
