Pod::Spec.new do |s|
  s.name             = 'MusicFreeNative'
  s.version          = '1.0.0'
  s.summary          = 'iOS native shims for MusicFree'
  s.description      = <<-DESC
  Local development pod that supplies the iOS counterparts of MusicFree's
  Android-only Kotlin native modules (NativeUtils / Mp3Util). Linked through
  CocoaPods, so no changes to MusicFree.xcodeproj/project.pbxproj are needed.
  DESC
  s.homepage         = 'https://github.com/maotoumao/MusicFree'
  s.license          = { :type => 'AGPL-3.0', :text => 'Derived from MusicFree, licensed under GNU AGPL-3.0.' }
  s.author           = { 'MusicFree iOS adapter' => 'noreply@example.com' }
  s.platform         = :ios, '15.1'

  # This pod is used as a :path development pod, so CocoaPods never fetches
  # this URL. It only exists to satisfy podspec validation.
  s.source           = { :git => 'https://github.com/maotoumao/MusicFree.git', :tag => 'v1.0.0-beta.4' }
  s.source_files     = 'MusicFreeNative/**/*.{h,m,mm}'
  s.requires_arc     = true
  s.dependency       = 'React-Core'
  s.frameworks       = 'Foundation', 'UIKit', 'AVFoundation', 'CoreMedia'
  s.pod_target_xcconfig = {
    'CLANG_ENABLE_MODULES' => 'YES',
    'DEFINES_MODULE' => 'YES'
  }
end
