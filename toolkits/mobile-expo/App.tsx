import { StatusBar } from 'expo-status-bar'
import { StyleSheet, Text, View } from 'react-native'

export default function App() {
  return (
    <View style={styles.root}>
      <StatusBar style="auto" />
      <Text style={styles.eyebrow}>Everflow · Expo</Text>
      <Text style={styles.title}>React Native starter</Text>
      <Text style={styles.body}>
        Run <Text style={styles.code}>npm run web</Text> and open Preview with an
        iPhone or Android device frame. Native simulators are not required in the
        sandbox.
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 28,
    backgroundColor: '#0f1419',
  },
  eyebrow: {
    color: '#7dd3c0',
    fontSize: 13,
    letterSpacing: 0.6,
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  title: {
    color: '#f4f7f5',
    fontSize: 26,
    fontWeight: '700',
    marginBottom: 12,
    textAlign: 'center',
  },
  body: {
    color: '#b7c0c8',
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
    maxWidth: 320,
  },
  code: {
    fontFamily: 'monospace',
    color: '#e8c07a',
  },
})
